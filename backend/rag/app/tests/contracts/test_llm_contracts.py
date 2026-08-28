"""Typed llm_agent request/reply contracts and debug-payload safety."""
from __future__ import annotations

import asyncio

import pytest

from app.core.config import RAGConfig
from app.services.conversation_backend_client import ConversationBackendClient
from app.services.conversation_events import CollectingConversationEmitter
from app.services.conversation_messages import (
    DownstreamRPCError,
    build_message_envelope,
    extract_reply_payload,
    extract_stream_event,
    normalize_llm_agent_response,
)
from app.tests._service_harness import (
    CaptureServiceClient,
    build_service,
)


def test_done_payload_uses_safe_debug_payloads_and_redacts_secret_values():
    service, backend, _ = build_service()
    backend.input_scan_message = "token=abc123"
    request = service.build_request({"question": "Show debug safely", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)

    asyncio.run(service.graph_runner.run(request, emitter))

    done_event = emitter.events[-1]
    safe_debug_payloads = done_event["data"]["safe_debug_payloads"]
    assert "debug_payloads" not in done_event["data"]
    assert "[redacted]" in str(safe_debug_payloads)
    assert "abc123" not in str(safe_debug_payloads)



def test_extract_reply_payload_preserves_structured_output_debug_metadata():
    shared = build_message_envelope(
        message_type="reply",
        action="content_risk_scan",
        source_service="llm_agent",
        target_service="rag",
        request_id="request-1",
        trace_id="trace-1",
        correlation_id="corr-1",
        payload={
            "request_type": "content_risk_scan",
            "status": "success",
            "raw_prompt": "",
            "system_prompt": "",
            "visible_reasoning_steps": [
                "Structured output extraction mode: multi_payload_last_valid",
                '__structured_output_debug__:{"payload_count":2,"selected_payload_index":1,"selection_policy":"last_valid","extraction_mode":"multi_payload_last_valid","candidates":[{"risk_level":"medium"},{"risk_level":"low"}]}',
            ],
            "raw_output": '{"risk_level":"medium"} {"risk_level":"low"}',
            "parsed_output": {
                "risk_level": "low",
                "categories": ["none"],
                "flags": [],
                "summary": "No material policy issues detected.",
            },
            "usage": {"provider": "fake"},
            "latency_ms": 12,
            "model": "test-model",
            "prompt_version": "content_risk_scan.v2",
            "trace": {"trace_id": "trace-1"},
            "errors": [],
        },
    )
    shared["success"] = True

    payload = extract_reply_payload(shared)

    assert payload["_structured_output_debug"]["payload_count"] == 2
    assert payload["_structured_output_debug"]["selected_payload_index"] == 1



def test_output_guardrails_debug_payloads_include_structured_output_candidates():
    service, backend, _ = build_service()

    async def risk_scan_with_candidates(request, text, stage):
        backend.calls.append({"type": "llm_agent", "request_type": "content_risk_scan", "stage": stage})
        return {
            "blocked": False,
            "stage": stage,
            "message": "clear",
            "raw_output": '{"risk_level":"medium"} {"risk_level":"low"}',
            "_structured_output_debug": {
                "payload_count": 2,
                "selected_payload_index": 1,
                "selection_policy": "last_valid",
                "extraction_mode": "multi_payload_last_valid",
                "candidates": [{"risk_level": "medium"}, {"risk_level": "low"}],
            },
        }

    backend.risk_scan = risk_scan_with_candidates
    request = service.build_request({"question": "Show debug safely", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)

    asyncio.run(service.graph_runner.run(request, emitter))

    done_event = emitter.events[-1]
    safe_debug_payloads = done_event["data"]["safe_debug_payloads"]
    assert safe_debug_payloads["output_safety_structured_output_selected_index"] == 1
    assert len(safe_debug_payloads["output_safety_structured_output_candidates"]) == 2



def test_query_rewrite_request_uses_typed_llm_agent_payload():
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(response={"rewritten_query": "rewrite:hello"})
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "hello"})

    asyncio.run(
        backend.query_rewrite(
            request,
            {
                "summary": "Earlier summary",
                "recent_messages": [
                    {"sender": "user", "message": "Earlier user message"},
                    {"sender": "assistant", "message": "Earlier assistant reply"},
                ],
                "memory_hits": [{"content": "User prefers concise answers"}],
            },
        )
    )

    payload = service_client.calls[0]["payload"]["payload"]
    assert payload["request_type"] == "query_rewrite"
    assert payload["metadata"]["conversation_id"] == request.conversation_id
    assert payload["metadata"]["graph_run_id"] == request.graph_run_id
    assert payload["input"]["query"] == "hello"
    assert payload["input"]["conversation_history"] == [
        {"role": "user", "content": "Earlier user message"},
        {"role": "assistant", "content": "Earlier assistant reply"},
    ]
    assert "Rewrite the user query" in payload["input"]["rewrite_goal"]



def test_content_risk_scan_request_uses_typed_llm_agent_payload():
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(response={"blocked": False})
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "hello"})

    asyncio.run(backend.risk_scan(request, "What can you help me with?", stage="input"))

    payload = service_client.calls[0]["payload"]["payload"]
    assert payload["request_type"] == "content_risk_scan"
    assert payload["metadata"]["stage"] == "input"
    assert payload["input"]["content"] == "What can you help me with?"
    assert payload["input"]["content_type"] == "user_input"
    assert "prompt_injection" in payload["input"]["policy_hints"]



def test_answer_evaluation_request_uses_typed_llm_agent_payload():
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(response={"verdict": "pass"})
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "What is RAG?"})

    asyncio.run(
        backend.evaluate_answer(
            request,
            answer="RAG is retrieval augmented generation.",
            retrieved_chunks=[{"text": "RAG combines retrieval and generation."}],
            mode="extended",
        )
    )

    payload = service_client.calls[0]["payload"]["payload"]
    assert payload["request_type"] == "answer_evaluation"
    assert payload["metadata"]["mode"] == "extended"
    assert payload["input"]["question"] == "What is RAG?"
    assert payload["input"]["answer"] == "RAG is retrieval augmented generation."
    # Passages, not bare strings: the judge names supporting passages by the
    # same numbers the answer's citation markers resolve against.
    assert payload["input"]["reference_context"] == [
        {
            "source_id": "passage_1",
            "text": "RAG combines retrieval and generation.",
            "locator": None,
        }
    ]



def test_answer_generation_request_uses_typed_llm_agent_payload():
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(
        response={"answer": "Regular answer"},
        stream_events=[
            build_message_envelope(
                message_type="stream_event",
                action="answer_generation",
                source_service="llm_agent",
                target_service="rag",
                request_id="stream-request",
                trace_id="trace-request",
                payload={"event_type": "llm.token", "data": {"token": "Regular ", "index": 0}},
                stream_to="rag.stream.test",
            ),
            build_message_envelope(
                message_type="stream_event",
                action="answer_generation",
                source_service="llm_agent",
                target_service="rag",
                request_id="stream-request",
                trace_id="trace-request",
                payload={"event_type": "llm.done", "data": {"finish_reason": "stop", "token_count": 1}},
                stream_to="rag.stream.test",
            ),
        ],
    )
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "What is RAG?", "mode": "extended"})

    streamed_tokens = []

    async def _consume_tokens(token, index):
        streamed_tokens.append((token, index))

    prompt = {
        "instructions": "Mode: extended\n\nConversation summary:\nEarlier summary",
        "retrieved_context": ["Chunk one", "Chunk two"],
        "recent_messages": [
            {"sender": "user", "message": "Earlier question"},
            {"sender": "assistant", "message": "Earlier answer"},
        ],
        "revision_attempted": False,
    }

    asyncio.run(backend.generate_answer(request, prompt, request.request_id, _consume_tokens))

    envelope = service_client.calls[0]["payload"]
    payload = envelope["payload"]
    assert envelope["stream_to"] == "rag.stream.test"
    assert service_client.calls[0]["stream"] is True
    assert streamed_tokens == [("Regular ", 0)]
    assert payload["request_type"] == "answer_generation"
    assert payload["metadata"]["request_id"] == request.request_id
    assert payload["input"]["question"] == "What is RAG?"
    assert payload["input"]["retrieved_context"] == ["Chunk one", "Chunk two"]
    assert payload["input"]["conversation_history"] == [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]
    assert "Mode: extended" in payload["input"]["instructions"]



def test_extract_reply_payload_normalizes_typed_llm_agent_reply():
    shared = build_message_envelope(
        message_type="reply",
        action="content_risk_scan",
        source_service="llm_agent",
        target_service="rag",
        request_id="request-1",
        trace_id="trace-1",
        correlation_id="corr-1",
        payload={
            "request_type": "content_risk_scan",
            "status": "success",
            "raw_prompt": "",
            "system_prompt": "",
            "visible_reasoning_steps": [],
            "raw_output": '{"risk_level":"low"}',
            "parsed_output": {
                "risk_level": "low",
                "categories": ["none"],
                "flags": [],
                "summary": "No material policy issues detected.",
            },
            "usage": {"provider": "fake"},
            "latency_ms": 12,
            "model": "test-model",
            "prompt_version": "content_risk_scan.v1",
            "trace": {"trace_id": "trace-1"},
            "errors": [],
        },
    )
    shared["success"] = True

    payload = extract_reply_payload(shared)

    assert payload["risk_level"] == "low"
    assert payload["blocked"] is False
    assert payload["message"] == "No material policy issues detected."



def test_normalize_llm_agent_response_marks_revision_when_verdict_is_revise():
    payload = normalize_llm_agent_response(
        {
            "request_type": "answer_evaluation",
            "status": "success",
            "parsed_output": {
                "review_id": "review-1",
                "verdict": "revise",
                "groundedness_score": 0.5,
                "completeness_score": 0.5,
                "safety_score": 1.0,
                "issues": ["add more grounding"],
                "revision_applied": False,
                "model_name": "test-model",
                "created_at": 1,
            },
            "model": "test-model",
            "prompt_version": "answer_evaluation.v1",
            "trace": {"trace_id": "trace-1"},
            "errors": [],
        }
    )

    assert payload["should_revise"] is True
    assert payload["verdict"] == "revise"



def test_extract_reply_payload_surfaces_internal_auth_error_explicitly():
    reply = {
        "message_type": "reply",
        "success": False,
        "error": {
            "code": "internal_auth_expired",
            "message": "Internal authentication context expired",
        },
    }

    with pytest.raises(DownstreamRPCError, match="internal_auth_expired") as exc_info:
        extract_reply_payload(reply)

    assert exc_info.value.code == "internal_auth_expired"



def test_extract_stream_event_supports_shared_stream_envelope():
    shared = build_message_envelope(
        message_type="stream_event",
        action="answer_generation",
        source_service="llm_agent",
        target_service="rag",
        request_id="request-1",
        trace_id="trace-1",
        correlation_id="corr-1",
        payload={"event_type": "llm.token", "data": {"token": "hello ", "index": 0}},
    )

    event = extract_stream_event(shared)

    assert event["request_id"] == "request-1"
    assert event["trace_id"] == "trace-1"
    assert event["event"] == "delta"
    assert event["text_delta"] == "hello "



