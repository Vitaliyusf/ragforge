"""RabbitMQ envelope, RPC handler and HTTP route transport behavior."""
from __future__ import annotations

import asyncio

import pytest

from app.core.config import RAGConfig
from app.core.errors import ServiceException
from app.messaging.rag_rpc_handler import build_reply_envelope, extract_request_payload
from app.services.conversation_backend_client import ConversationBackendClient
from app.services.websocket_service import WebSocketService
from app.tests._service_harness import (
    TEST_IDENTITY,
    CaptureServiceClient,
    DummyLogger,
    HTTPRouteService,
    TestClient,
    build_http_client,
    build_service,
)


def test_websocket_error_builder_creates_complete_error_envelope():
    service, _, _ = build_service()
    websocket_service = WebSocketService(service, DummyLogger())
    websocket_service.register_connection("socket-1", TEST_IDENTITY)

    event = websocket_service.build_error_event(
        "socket-1",
        {"question": "", "mode": "regular"},
        code="websocket_request_error",
        failed_node="question",
        retryable=True,
        message="Question is required",
    )

    assert event["type"] == "error"
    assert event["request_id"]
    assert event["trace_id"]
    assert event["conversation_id"]
    assert event["turn_id"]
    assert event["data"]["code"] == "websocket_request_error"
    assert event["data"]["failed_node"] == "question"
    assert event["data"]["origin"]["service"] == "rag"
    assert event["data"]["origin"]["location"] == "websocket_service:handle_question"
    assert event["data"]["details"] == {}



def test_config_defaults_use_rabbitmq_routing_keys():
    config = RAGConfig()
    assert config.rabbitmq_queue == "rag"
    assert config.memory_routing_key == "memory"
    assert config.vector_db_routing_key == "vector_db"
    assert config.embedding_routing_key == "embedding"
    assert config.llm_agent_routing_key == "llm_agent"



def test_rag_rpc_handler_extracts_payload_and_builds_canonical_reply():
    body = {
        "action": "request",
        "source_service": "gateway",
        "request_id": "request-1",
        "trace_id": "trace-1",
        "correlation_id": "untrusted-correlation",
        "payload": {"question": "What is RAG?", "answer_mode": "quick"},
    }

    request_data = extract_request_payload(body, "broker-correlation")
    reply = build_reply_envelope(
        body,
        {"answer": "Retrieval-augmented generation", "sources": []},
        "broker-correlation",
    )

    assert request_data["question"] == "What is RAG?"
    assert request_data["request_id"] == "request-1"
    assert request_data["trace_id"] == "trace-1"
    assert request_data["correlation_id"] == "broker-correlation"
    assert reply["message_type"] == "reply"
    assert reply["source_service"] == "rag"
    assert reply["target_service"] == "gateway"
    assert reply["correlation_id"] == "broker-correlation"
    assert reply["success"] is True
    assert reply["payload"]["answer"] == "Retrieval-augmented generation"



def test_backend_client_builds_shared_rabbitmq_envelope():
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(response={"memories": []})
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "hello", "owner_id": "user-1", "owner_type": "user"})

    asyncio.run(backend.get_relevant_memories(request, depth="light"))

    call = service_client.calls[0]
    assert call["routing_key"] == "memory"
    envelope = call["payload"]
    assert envelope["message_type"] == "query"
    assert envelope["action"] == "get_relevant_memories"
    assert envelope["source_service"] == "rag"
    assert envelope["target_service"] == "memory"
    assert "reply_to" not in envelope
    assert envelope["request_id"] == request.request_id
    assert envelope["trace_id"] == request.trace_id
    assert envelope["payload"]["request_id"] == request.request_id
    assert envelope["payload"]["trace_id"] == request.trace_id
    assert envelope["payload"]["owner_id"] == TEST_IDENTITY.user_id
    assert envelope["payload"]["owner_type"] == "user"
    assert envelope["payload"]["graph_run_id"] == request.graph_run_id
    assert isinstance(envelope["timestamp"], int)



@pytest.mark.skipif(TestClient is None, reason="fastapi test client dependencies are unavailable")
def test_http_query_route_returns_compact_response():
    service = HTTPRouteService()

    with build_http_client(service) as client:
        response = client.post("/api/v1/query", json={"question": "HTTP hello", "mode": "extended"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "HTTP answer",
        "sources": ["HTTP source"],
        "review": {"verdict": "pass"},
    }
    assert service.calls == [
        {
            "question": "HTTP hello",
            "model": None,
            "mode": "extended",
            "answer_mode": "quick",
        }
    ]


@pytest.mark.skipif(TestClient is None, reason="fastapi test client dependencies are unavailable")
def test_http_query_route_maps_service_exception_to_503():
    service = HTTPRouteService(exc=ServiceException("downstream unavailable"))

    with build_http_client(service) as client:
        response = client.post("/api/v1/query", json={"question": "HTTP fail"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Service temporarily unavailable"}


@pytest.mark.skipif(TestClient is None, reason="fastapi test client dependencies are unavailable")
def test_http_query_route_maps_unexpected_exception_to_500():
    service = HTTPRouteService(exc=RuntimeError("boom"))

    with build_http_client(service) as client:
        response = client.post("/api/v1/query", json={"question": "HTTP boom"})

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected error occurred"}

