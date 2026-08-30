"""Shared fakes and service builders for the LangGraph-backed `rag` runtime.

Cross-domain on purpose: core, contract, metrics and trace tests all drive a
real `RAGService` against these fakes rather than reimplementing a backend.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from shared.auth import AuthIdentity
from shared.context import bound_context

from app.core.config import RAGConfig
from app.rest.v1.rag import get_rag_service, require_internal_identity
from app.rest.v1.rag import router as rag_router
from app.services.conversation_persistence import InMemoryConversationStore
from app.services.conversation_tracing import ConversationTracer
from app.services.rag_service import RAGService

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - optional test dependency
    TestClient = None


TEST_IDENTITY = AuthIdentity(
    tenant_id="tenant-a",
    user_id="admin-a",
    role="admin",
    email="admin@example.com",
    admin_id="admin-a",
    session_id="session-a",
)


@pytest.fixture(autouse=True)
def authenticated_request_context():
    """Exercise service tests behind the same trusted identity boundary as runtime."""
    with bound_context(**TEST_IDENTITY.to_dict()):
        yield

class DummyLogger:
    def log(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class RecordingLogger(DummyLogger):
    def __init__(self):
        self.events: list[str] = []

    def info(self, event, *args, **kwargs):
        self.events.append(event)

    def exception(self, event, *args, **kwargs):
        self.events.append(event)


class FakeBackendClient:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self.published: list[dict[str, Any]] = []
        self.fail_generation = False
        self.input_scan_message = "input accepted"
        self.output_scan_message = "clear"

    async def get_relevant_memories(self, request, depth):
        self.calls.append({"type": "memory", "depth": depth, "request_id": request.request_id})
        return {"memories": [{"content": f"{depth} memory"}]}

    async def search_chunks(
        self,
        request,
        query,
        retrieval_plan=None,
        pass_name="pass_one",
        *,
        top_k=None,
    ):
        self.calls.append({"type": "vector_db", "pass_name": pass_name, "query": query})
        if pass_name == "pass_two":
            return {
                "chunks": [
                    {"chunk_id": "c2", "text": "Pass two chunk", "score": 0.91, "source": "file-b.md"}
                ]
            }
        if request.mode == "extended":
            return {
                "chunks": [
                    {"chunk_id": "c1", "text": "Pass one chunk", "score": 0.31, "source": "file-a.md"}
                ]
            }
        return {
            "chunks": [
                {"chunk_id": "c1", "text": "Regular chunk", "score": 0.82, "source": "file-a.md"}
            ]
        }

    async def query_rewrite(self, request, context):
        self.calls.append({"type": "llm_agent", "request_type": "query_rewrite"})
        return {
            "rewritten_query": f"rewrite:{request.user_message}",
            "subqueries": ["subquery one"],
            "pass_two_hints": ["fallback query"] if "second retrieval" in request.user_message.lower() else [],
        }

    async def risk_scan(self, request, text, stage):
        self.calls.append({"type": "llm_agent", "request_type": "content_risk_scan", "stage": stage})
        return {
            "blocked": False,
            "stage": stage,
            "message": self.input_scan_message if stage == "input" else self.output_scan_message,
            "token": "super-secret-token",
        }

    async def evaluate_answer(self, request, answer, retrieved_chunks, mode):
        self.calls.append(
            {
                "type": "llm_agent",
                "request_type": "answer_evaluation",
                "mode": mode,
                "retrieved_chunks": list(retrieved_chunks),
            }
        )
        if mode == "extended" and "Draft answer" in answer:
            return {
                "review_id": f"review-{request.turn_id}",
                "verdict": "revise",
                "groundedness_score": 0.65,
                "completeness_score": 0.62,
                "safety_score": 0.99,
                "issues": ["add more grounding"],
                "should_revise": True,
                "model_name": "fake-evaluator",
            }
        return {
            "review_id": f"review-{request.turn_id}",
            "verdict": "pass",
            "groundedness_score": 0.92,
            "completeness_score": 0.88,
            "safety_score": 1.0,
            "issues": [],
            "should_revise": False,
            "model_name": "fake-evaluator",
        }

    async def generate_answer(self, request, prompt, stream_request_id, token_callback):
        self.calls.append(
            {
                "type": "llm_agent",
                "request_type": "answer_generation",
                "prompt": prompt["instructions"],
                "retrieved_context": list(prompt["retrieved_context"]),
            }
        )
        if self.fail_generation:
            raise RuntimeError("generation failed")
        if "Fix these issues" in prompt["instructions"]:
            answer = "Revised final answer"
        elif "Mode: extended" in prompt["instructions"]:
            answer = "Draft answer for extended flow"
        else:
            answer = "Regular answer"
        for index, part in enumerate(answer.split(" ")):
            await token_callback(f"{part} ", index)
        return {"answer": answer, "model_name": "fake-generator", "raw_output": answer}

    def publish_turn_started(self, request):
        self.published.append({"topic": "rag.turn.started", "request_id": request.request_id})

    def publish_answer_generated(self, request, chunk_count):
        self.published.append({"topic": "rag.answer.generated", "chunk_count": chunk_count})

    def publish_answer_evaluated(self, request, verdict):
        self.published.append({"topic": "rag.answer.evaluated", "verdict": verdict})

    def publish_feedback_received(self, request, feedback_type):
        self.published.append({"topic": "rag.feedback.received", "feedback_type": feedback_type})

    def publish_memory_write_requested(self, payload):
        self.published.append({"topic": "memory.write.requested", **payload})


class CaptureServiceClient:
    def __init__(
        self,
        response: dict[str, Any] | None = None,
        responses: list[dict[str, Any]] | None = None,
        responder=None,
        stream_events: list[dict[str, Any]] | None = None,
    ):
        self.calls: list[dict[str, Any]] = []
        self.response = response or {}
        self.responses = list(responses or [])
        self.responder = responder
        self.stream_events = list(stream_events or [])

    async def request(self, routing_key: str, payload: dict[str, Any], timeout: float = 10.0):
        payload = dict(payload)
        payload["correlation_id"] = payload.get("correlation_id") or str(uuid.uuid4())
        self.calls.append({"routing_key": routing_key, "payload": payload, "timeout": timeout})
        if self.responder is not None:
            result = self.responder(routing_key, payload, timeout)
            if asyncio.iscoroutine(result):
                return await result
            return result
        if self.responses:
            return self.responses.pop(0)
        return self.response

    async def request_stream(
        self,
        routing_key: str,
        payload: dict[str, Any],
        timeout: float,
        stream_callback,
    ):
        copied = dict(payload)
        copied["stream_to"] = "rag.stream.test"
        self.calls.append(
            {
                "routing_key": routing_key,
                "payload": copied,
                "timeout": timeout,
                "stream": True,
            }
        )
        for event in self.stream_events:
            await stream_callback(event)
        if self.responses:
            return self.responses.pop(0)
        return self.response

    async def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        self.calls.append({"routing_key": routing_key, "payload": dict(payload), "publish": True})


def build_service():
    config = RAGConfig(
        conversation_store_type="in_memory",
        enable_langsmith_tracing=False,
        feedback_memory_threshold=3,
        pass_two_chunk_threshold=2,
        pass_two_score_threshold=0.5,
    )
    store = InMemoryConversationStore(config)
    backend = FakeBackendClient()
    service = RAGService(
        backend_client=backend,
        conversation_store=store,
        logger=DummyLogger(),
        config=config,
        tracer=ConversationTracer(config),
    )
    return service, backend, store


class HTTPRouteService:
    def __init__(self, result: dict[str, Any] | None = None, exc: Exception | None = None):
        self.result = result or {"answer": "HTTP answer", "sources": ["HTTP source"], "review": {"verdict": "pass"}}
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    async def query(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.result


def build_http_client(service: HTTPRouteService):
    app = FastAPI()
    app.include_router(rag_router, prefix="/api/v1")
    app.dependency_overrides[get_rag_service] = lambda: service
    app.dependency_overrides[require_internal_identity] = lambda: AuthIdentity(
        tenant_id="tenant-a",
        user_id="service-a",
        role="service",
        admin_id="admin-a",
    )
    return TestClient(app)

