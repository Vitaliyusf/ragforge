"""Tests for the LangGraph-backed `rag` runtime."""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI

from app.core.config import RAGConfig
from app.core.errors import ServiceException
from app.rest.v1.rag import get_rag_service, require_internal_identity, router as rag_router
from app.services.conversation_events import CollectingConversationEmitter
from app.services.conversation_backend_client import ConversationBackendClient
from app.services.conversation_messages import (
    DownstreamRPCError,
    build_message_envelope,
    extract_reply_payload,
    extract_stream_event,
    normalize_llm_agent_response,
)
from app.services.conversation_persistence import (
    AsyncConversationPersistence,
    InMemoryConversationStore,
)
from app.services.conversation_tracing import ConversationTracer
from app.services.conversation_types import build_initial_state
from app.services.rag_service import RAGService
from app.services.retrieval_trace import RetrievalTrace
from app.services.websocket_service import WebSocketService
from app.messaging.rag_rpc_handler import build_reply_envelope, extract_request_payload
from shared.auth import AuthError, AuthIdentity
from shared.context import bound_context, get_context

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
        self.events: List[str] = []

    def info(self, event, *args, **kwargs):
        self.events.append(event)

    def exception(self, event, *args, **kwargs):
        self.events.append(event)


class FakeBackendClient:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.published: List[Dict[str, Any]] = []
        self.fail_generation = False
        self.input_scan_message = "input accepted"
        self.output_scan_message = "clear"

    async def get_relevant_memories(self, request, depth):
        self.calls.append({"type": "memory", "depth": depth, "request_id": request.request_id})
        return {"memories": [{"content": f"{depth} memory"}]}

    async def search_chunks(self, request, query, retrieval_plan=None, pass_name="pass_one"):
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
        self.calls.append({"type": "llm_agent", "request_type": "answer_evaluation", "mode": mode})
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
        self.calls.append({"type": "llm_agent", "request_type": "answer_generation", "prompt": prompt["instructions"]})
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
        response: Dict[str, Any] | None = None,
        responses: List[Dict[str, Any]] | None = None,
        responder=None,
        stream_events: List[Dict[str, Any]] | None = None,
    ):
        self.calls: List[Dict[str, Any]] = []
        self.response = response or {}
        self.responses = list(responses or [])
        self.responder = responder
        self.stream_events = list(stream_events or [])

    async def request(self, routing_key: str, payload: Dict[str, Any], timeout: float = 10.0):
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
        payload: Dict[str, Any],
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

    async def publish(self, routing_key: str, payload: Dict[str, Any]) -> None:
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
    def __init__(self, result: Dict[str, Any] | None = None, exc: Exception | None = None):
        self.result = result or {"answer": "HTTP answer", "sources": ["HTTP source"], "review": {"verdict": "pass"}}
        self.exc = exc
        self.calls: List[Dict[str, Any]] = []

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


def test_normalize_legacy_answer_mode_quick_to_regular():
    service, _, _ = build_service()
    request = service.build_request({"question": "hello", "answer_mode": "quick"})
    assert request.mode == "regular"
    assert request.owner_type == "user"
    assert request.owner_id == TEST_IDENTITY.user_id
    assert request.tenant_id == TEST_IDENTITY.tenant_id


def test_build_request_rejects_missing_authenticated_identity():
    service, _, _ = build_service()

    with bound_context(tenant_id=None, user_id=None, role=None, admin_id=None, session_id=None):
        with pytest.raises(AuthError, match="authenticated identity is missing"):
            service.build_request({"question": "hello"})


def test_regular_flow_happy_path_streams_tokens_and_review():
    service, backend, _ = build_service()
    request = service.build_request({"question": "What is RAG?", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)

    result = asyncio.run(service.graph_runner.run(request, emitter))

    assert result["answer"] == "Regular answer"
    assert emitter.events[-1]["type"] == "done"
    assert any(event["type"] == "token" for event in emitter.events)
    review_event = next(event for event in emitter.events if event["type"] == "answer_review")
    assert set(review_event["data"].keys()) == {
        "review_id",
        "verdict",
        "groundedness_score",
        "completeness_score",
        "safety_score",
        "issues",
        # Summary hallucination judgements are public; the claims array that
        # produced them is not - see `_public_review`.
        "hallucination_verdict",
        "unsupported_claim_count",
        "revision_applied",
        "model_name",
        "created_at",
    }
    assert "claims" not in review_event["data"]
    assert any(call["type"] == "memory" and call["depth"] == "light" for call in backend.calls)
    assert any(call["type"] == "vector_db" and call["pass_name"] == "regular" for call in backend.calls)
    done_event = emitter.events[-1]
    assert "safe_debug_payloads" in done_event["data"]
    assert "debug_payloads" not in done_event["data"]
    assert done_event["data"]["review_summary"]["verdict"] == "pass"
    first_source = done_event["data"]["sources"][0]
    for key in [
        "file_id",
        "document_id",
        "chunk_id",
        "chunk_index",
        "chunk_version",
        "text",
        "text_preview",
        "source_name",
        "retrieval_allowed",
        "review_status",
        "issue_flags",
        "created_at",
    ]:
        assert key in first_source


def test_extended_flow_runs_second_retrieval_and_revises_once():
    service, backend, _ = build_service()
    request = service.build_request(
        {"question": "Need second retrieval and revise this answer", "mode": "extended"}
    )
    emitter = CollectingConversationEmitter(request)

    result = asyncio.run(service.graph_runner.run(request, emitter))

    assert result["answer"] == "Revised final answer"
    assert any(call["type"] == "vector_db" and call["pass_name"] == "pass_two" for call in backend.calls)
    generation_calls = [
        call for call in backend.calls
        if call["type"] == "llm_agent" and call["request_type"] == "answer_generation"
    ]
    assert len(generation_calls) == 2
    review_events = [event for event in emitter.events if event["type"] == "answer_review"]
    assert review_events[-1]["data"]["revision_applied"] is True
    assert emitter.events[-1]["type"] == "done"


def test_extended_pass_one_retrieval_is_bounded_and_deterministic():
    service, backend, _ = build_service()
    service.graph_runner.config.extended_retrieval_max_concurrency = 2
    service.graph_runner.config.pass_two_chunk_threshold = 1
    service.graph_runner.config.pass_two_score_threshold = 0.1
    queries = ["rewrite", "slow subquery", "fast subquery", "last subquery"]
    delays = {
        "rewrite": 0.04,
        "slow subquery": 0.03,
        "fast subquery": 0.01,
        "last subquery": 0.0,
    }
    active = 0
    max_active = 0
    saw_overlap = asyncio.Event()
    propagated = []

    async def rewrite(request, context):
        return {"rewritten_query": queries[0], "subqueries": queries[1:]}

    async def search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        nonlocal active, max_active
        assert pass_name == "pass_one"
        active += 1
        max_active = max(max_active, active)
        if active > 1:
            saw_overlap.set()
        propagated.append(
            (
                request.request_id,
                request.trace_id,
                get_context().get("tenant_id"),
                retrieval_plan["rewritten_query"],
            )
        )
        try:
            await asyncio.sleep(delays[query])
        finally:
            active -= 1
        return {
            "chunks": [
                {
                    "chunk_id": query,
                    "text": query,
                    "score": 0.8,
                    "source": f"{query}.md",
                }
            ]
        }

    backend.query_rewrite = rewrite
    backend.search_chunks = search_chunks
    request = service.build_request({"question": "parallelize", "mode": "extended"})
    result = asyncio.run(
        service.graph_runner.run(request, CollectingConversationEmitter(request))
    )

    assert saw_overlap.is_set()
    assert max_active == 2
    assert [chunk["chunk_id"] for chunk in result["sources"]] == queries
    assert propagated == [
        (request.request_id, request.trace_id, TEST_IDENTITY.tenant_id, queries[0])
    ] * len(queries)


def test_extended_parallel_retrieval_preserves_downstream_error_policy():
    service, backend, _ = build_service()
    service.graph_runner.config.extended_retrieval_max_concurrency = 2

    async def rewrite(request, context):
        return {"rewritten_query": "ok", "subqueries": ["fails", "cancelled"]}

    async def search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        if query == "fails":
            await asyncio.sleep(0.01)
            raise ValueError("subquery retrieval failed")
        await asyncio.sleep(0.03)
        return {
            "chunks": [
                {"chunk_id": query, "text": query, "score": 0.8, "source": "source.md"}
            ]
        }

    backend.query_rewrite = rewrite
    backend.search_chunks = search_chunks
    request = service.build_request({"question": "parallelize", "mode": "extended"})
    result = asyncio.run(
        service.graph_runner.run(request, CollectingConversationEmitter(request))
    )

    assert result["outcome"] == "failed"
    assert result["error"] == "subquery retrieval failed"
    assert result["error_class"] == "ValueError"
    assert result["failed_node"] == "retrieve_pass_one"
    assert result["sources"] == []


def test_pass_two_candidates_are_globally_ranked_and_deduped():
    service, backend, _ = build_service()
    service.graph_runner.config.top_k_documents = 2

    async def search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        backend.calls.append({"type": "vector_db", "pass_name": pass_name, "query": query})
        if pass_name == "pass_two":
            return {
                "chunks": [
                    {"chunk_id": "c1", "text": "Duplicate", "score": 0.5, "source": "one.md"},
                    {"chunk_id": "c2", "text": "Best Pass2", "score": 0.95, "source": "two.md"},
                    {"chunk_id": "c4", "text": "Tied Pass2", "score": 0.7, "source": "four.md"},
                ]
            }
        return {
            "chunks": [
                {"chunk_id": "c1", "text": "Best duplicate", "score": 0.8, "source": "one.md"},
                {"chunk_id": "c3", "text": "Tied Pass1", "score": 0.7, "source": "three.md"},
            ]
        }

    backend.search_chunks = search_chunks
    request = service.build_request(
        {"question": "Need second retrieval and revise this answer", "mode": "extended"}
    )
    emitter = CollectingConversationEmitter(request)

    result = asyncio.run(service.graph_runner.run(request, emitter))

    chunk_ids = [chunk["chunk_id"] for chunk in result["sources"]]
    assert chunk_ids == ["c2", "c1", "c3", "c4"]
    assert chunk_ids[: service.graph_runner.config.top_k_documents] == ["c2", "c1"]
    assert chunk_ids.count("c1") == 1
    assert result["sources"][1]["score"] == 0.8


def test_error_path_emits_single_terminal_error():
    service, backend, _ = build_service()
    logger = RecordingLogger()
    service.graph_runner.logger = logger
    backend.fail_generation = True
    request = service.build_request({"question": "Break generation", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)

    result = asyncio.run(service.graph_runner.run(request, emitter))

    terminal_events = [event for event in emitter.events if event["type"] in {"done", "error"}]
    assert result["error"] == "generation failed"
    assert len(terminal_events) == 1
    assert terminal_events[0]["type"] == "error"
    assert "conversation graph execution failed" in logger.events


def run_traced_turn(service, question: str, mode: str = "regular"):
    """Run one turn with a collector attached, as the eval harness does."""
    trace = RetrievalTrace()
    request = service.build_request({"question": question, "mode": mode})
    emitter = CollectingConversationEmitter(request)
    result = asyncio.run(
        service.graph_runner.run(request, emitter, retrieval_trace=trace)
    )
    return result, trace


def test_a_generation_failure_is_an_explicit_failure_that_keeps_its_context():
    """The retrieval that succeeded is not unmade by the generator failing."""
    service, backend, _ = build_service()
    backend.fail_generation = True

    result, trace = run_traced_turn(service, "Break generation")

    assert result["outcome"] == "failed"
    assert result["error"] == "generation failed"
    assert result["error_class"] == "RuntimeError"
    assert result["failed_node"] == "generate_answer"
    assert [chunk["chunk_id"] for chunk in result["sources"]] == ["c1"]
    final = trace.final_context_stage()
    assert final is not None
    assert [candidate["chunk_id"] for candidate in final["candidates"]] == ["c1"]


def test_an_evaluation_failure_keeps_the_context_the_answer_was_generated_from():
    """The judge is downstream of retrieval; its failure is not a miss."""
    service, backend, _ = build_service()

    async def unparseable_review(request, answer, retrieved_chunks, mode):
        raise ValueError("structured output validation failed")

    backend.evaluate_answer = unparseable_review

    result, trace = run_traced_turn(service, "What is RAG?")

    assert result["outcome"] == "failed"
    assert result["error_class"] == "ValueError"
    assert result["failed_node"] == "evaluate_answer_light"
    assert [chunk["chunk_id"] for chunk in result["sources"]] == ["c1"]
    assert trace.final_context_stage() is not None


def test_a_failure_before_retrieval_reports_no_context_at_all():
    """An unknown context is absent, never an empty one — that would score."""
    service, backend, _ = build_service()

    async def unavailable(request, query, retrieval_plan=None, pass_name="pass_one"):
        raise RuntimeError("vector store unavailable")

    backend.search_chunks = unavailable

    result, trace = run_traced_turn(service, "What is RAG?")

    assert result["outcome"] == "failed"
    assert result["error_class"] == "RuntimeError"
    assert result["failed_node"] == "retrieve_chunks_once"
    assert result["sources"] == []
    assert trace.final_context_stage() is None


def test_a_successful_turn_still_reports_success_and_its_context():
    service, _, _ = build_service()

    result, trace = run_traced_turn(service, "What is RAG?")

    assert result["outcome"] == "success"
    assert "error" not in result
    assert [chunk["chunk_id"] for chunk in result["sources"]] == ["c1"]
    assert trace.final_context_stage()["kept_count"] == 1


def test_input_guardrail_block_is_a_structured_outcome_not_a_graph_failure():
    service, backend, _ = build_service()
    logger = RecordingLogger()
    service.graph_runner.logger = logger

    async def block_input(request, text, stage):
        return {"blocked": stage == "input", "message": "sensitive request", "stage": stage}

    backend.risk_scan = block_input
    request = service.build_request({"question": "private text", "mode": "regular"})
    result = asyncio.run(service.graph_runner.run(request, CollectingConversationEmitter(request)))

    assert result["outcome"] == "guardrail_blocked"
    assert result["guardrail_stage"] == "input"
    assert "error" not in result
    assert "conversation graph execution failed" not in logger.events
    assert "conversation guardrail blocked" in logger.events


def test_output_guardrail_block_preserves_its_stage_in_the_result():
    service, backend, _ = build_service()

    async def block_output(request, text, stage):
        return {
            "blocked": stage == "output",
            "safe_output": "Safe response",
            "message": "blocked",
            "stage": stage,
        }

    backend.risk_scan = block_output
    request = service.build_request({"question": "normal question", "mode": "regular"})
    result = asyncio.run(service.graph_runner.run(request, CollectingConversationEmitter(request)))

    assert result["outcome"] == "guardrail_blocked"
    assert result["guardrail_stage"] == "output"


def test_checkpoint_restore_resumes_from_after_generation_without_retrieval():
    service, backend, store = build_service()
    request = service.build_request({"question": "Resume me", "mode": "regular"})
    state = build_initial_state(request)
    state["retrieved_chunks"] = [{"chunk_id": "c1", "text": "Checkpoint chunk", "score": 0.8, "source": "file.md", "metadata": {}}]
    state["draft_answer"] = {"text": "Checkpoint draft answer", "sources": state["retrieved_chunks"]}
    store.save_checkpoint(
        {
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "request_id": request.request_id,
            "trace_id": request.trace_id,
            "node": "generate_answer",
            "stage": "after_generation",
            "status": "ok",
            "state": state,
            "created_at": "2026-03-17T00:00:00Z",
        }
    )
    emitter = CollectingConversationEmitter(request)

    result = asyncio.run(service.graph_runner.run(request, emitter, resume=True))

    assert result["answer"] == "Checkpoint draft answer"
    assert not any(call["type"] == "vector_db" for call in backend.calls)
    assert any(call["type"] == "llm_agent" and call["request_type"] == "answer_evaluation" for call in backend.calls)
    assert emitter.events[-1]["type"] == "done"


def test_async_persistence_is_non_blocking_and_concurrency_bounded():
    class DelayedStore(InMemoryConversationStore):
        def __init__(self):
            super().__init__(RAGConfig(conversation_store_type="in_memory"))
            self.active_calls = 0
            self.max_active_calls = 0
            self.call_lock = threading.Lock()

        def save_checkpoint(self, document: Dict[str, Any]) -> None:
            with self.call_lock:
                self.active_calls += 1
                self.max_active_calls = max(self.max_active_calls, self.active_calls)
            try:
                time.sleep(0.05)
                super().save_checkpoint(document)
            finally:
                with self.call_lock:
                    self.active_calls -= 1

    async def exercise() -> DelayedStore:
        store = DelayedStore()
        persistence = AsyncConversationPersistence(store, max_concurrency=2)
        tasks = [
            asyncio.create_task(persistence.save_checkpoint({"sequence": sequence}))
            for sequence in range(4)
        ]

        await asyncio.sleep(0.01)
        assert not all(task.done() for task in tasks)

        await asyncio.gather(*tasks)
        return store

    store = asyncio.run(exercise())

    assert len(store.checkpoints) == 4
    assert store.max_active_calls == 2


def test_feedback_persistence_and_memory_threshold():
    service, backend, store = build_service()

    for turn_number in range(3):
        result = asyncio.run(
            service.handle_feedback(
                "answer_feedback",
                {
                    "conversation_id": "conversation-1",
                    "turn_id": f"turn-{turn_number}",
                    "request_id": f"request-{turn_number}",
                    "trace_id": f"trace-{turn_number}",
                    "comment": "Please keep answers concise",
                },
            )
        )
        assert result["stored"] is True

    assert len(store.user_feedback) == 3
    memory_events = [event for event in backend.published if event["topic"] == "memory.write.requested"]
    assert len(memory_events) == 1
    assert memory_events[0]["signal"] == "user_prefers_concise_answers"
    assert memory_events[0]["owner_type"] == "user"
    assert memory_events[0]["owner_id"] == TEST_IDENTITY.user_id
    assert len(memory_events[0]["supporting_turn_ids"]) == 3

    asyncio.run(
        service.handle_feedback(
            "answer_feedback",
            {
                "conversation_id": "conversation-1",
                "turn_id": "turn-3",
                "request_id": "request-3",
                "trace_id": "trace-3",
                "comment": "Keep answers concise please",
            },
        )
    )
    memory_events = [event for event in backend.published if event["topic"] == "memory.write.requested"]
    assert len(memory_events) == 1


def test_feedback_and_turns_are_persisted():
    service, _, store = build_service()
    request = service.build_request({"question": "Persist this", "mode": "regular", "conversation_id": "conversation-a"})
    emitter = CollectingConversationEmitter(request)

    asyncio.run(service.graph_runner.run(request, emitter))
    asyncio.run(
        service.handle_feedback(
            "flow_feedback",
            {
                "conversation_id": request.conversation_id,
                "turn_id": request.turn_id,
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "comment": "Prefer step-by-step replies",
            },
        )
    )

    assert f"{TEST_IDENTITY.tenant_id}:{TEST_IDENTITY.user_id}:{request.turn_id}" in store.turns
    assert f"{TEST_IDENTITY.tenant_id}:{TEST_IDENTITY.user_id}:{request.conversation_id}" in store.summaries
    assert len(store.checkpoints) >= 5
    assert len(store.flow_feedback) == 1


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


def test_search_chunks_embeds_query_before_vector_search():
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(
        responses=[
            {"embedding": [0.1, 0.2, 0.3]},
            {"results": [{"id": "chunk-1", "score": 0.9, "payload": {"chunk_id": "chunk-1"}}]},
        ]
    )
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "hello"})

    response = asyncio.run(backend.search_chunks(request, "hello", {"decision": "rewrite"}, "pass_one"))

    assert response["results"][0]["payload"]["chunk_id"] == "chunk-1"
    assert len(service_client.calls) == 2

    embedding_call = service_client.calls[0]
    assert embedding_call["routing_key"] == "embedding"
    assert embedding_call["payload"]["action"] == "embed"
    assert embedding_call["payload"]["payload"]["text"] == "hello"

    vector_call = service_client.calls[1]
    assert vector_call["routing_key"] == "vector_db"
    envelope = vector_call["payload"]
    assert envelope["message_type"] == "query"
    assert envelope["action"] == "search_chunks"
    assert envelope["payload"]["query_vector"] == [0.1, 0.2, 0.3]
    assert envelope["payload"]["query"] == "hello"
    assert envelope["payload"]["pass_name"] == "pass_one"
    # Production retrieval keeps the configured answer-context depth: the
    # eval harness's wider candidate depth must not leak into a user turn.
    assert envelope["payload"]["top_k"] == config.top_k_documents
    assert "reply_to" not in envelope


def test_search_chunks_top_k_can_be_overridden_for_an_eval_sweep():
    """The retrieval eval must be able to ask beyond `top_k_documents`.

    Recall@20 is only a measurement if twenty candidates were requested;
    raising `top_k_documents` to get there would change what every user turn
    is answered from.
    """
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(
        responses=[{"embedding": [0.1, 0.2, 0.3]}, {"results": []}]
    )
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "hello"})

    asyncio.run(backend.search_chunks(request, "hello", {}, "eval", top_k=20))

    assert config.top_k_documents == 6
    assert service_client.calls[1]["payload"]["payload"]["top_k"] == 20


def test_search_chunks_raises_when_embedding_reply_is_empty():
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(response={"embedding": []})
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "hello"})

    with pytest.raises(RuntimeError, match="returned no query_vector"):
        asyncio.run(backend.search_chunks(request, "hello"))


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


def test_extract_reply_payload_supports_shared_and_legacy_shapes():
    shared = build_message_envelope(
        message_type="reply",
        action="search_chunks",
        source_service="vector_db",
        target_service="rag",
        request_id="request-1",
        trace_id="trace-1",
        correlation_id="corr-1",
        payload={"chunks": [{"chunk_id": "c1"}]},
    )
    shared["success"] = True

    legacy = {"correlation_id": "corr-legacy", "data": {"chunks": [{"chunk_id": "legacy"}]}}

    assert extract_reply_payload(shared)["chunks"][0]["chunk_id"] == "c1"
    assert extract_reply_payload(legacy)["chunks"][0]["chunk_id"] == "legacy"


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


def test_checkpoint_restore_reuses_graph_run_id_and_owner_identity():
    service, _, store = build_service()
    request = service.build_request({"question": "Resume me", "mode": "regular"})
    state = build_initial_state(request)
    state["retrieved_chunks"] = [{"chunk_id": "c1", "text": "Checkpoint chunk", "score": 0.8, "source": "file.md", "metadata": {}}]
    state["draft_answer"] = {"text": "Checkpoint draft answer", "sources": state["retrieved_chunks"]}
    store.save_checkpoint(
        {
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "request_id": request.request_id,
            "trace_id": request.trace_id,
            "graph_run_id": "graph-run-1",
            "owner_id": "user-7",
            "owner_type": "user",
            "node": "generate_answer",
            "stage": "after_generation",
            "status": "ok",
            "state": state,
            "created_at": "2026-03-17T00:00:00Z",
        }
    )
    resumed_request = service.build_request(
        {
            "question": "Resume me",
            "mode": "regular",
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "request_id": request.request_id,
            "trace_id": request.trace_id,
        }
    )
    emitter = CollectingConversationEmitter(resumed_request)

    asyncio.run(service.graph_runner.run(resumed_request, emitter, resume=True))

    assert resumed_request.graph_run_id == "graph-run-1"
    assert resumed_request.owner_id == TEST_IDENTITY.user_id
    assert resumed_request.owner_type == "user"


def test_retrieval_filters_ineligible_chunks():
    service, backend, _ = build_service()

    async def fake_search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        backend.calls.append({"type": "vector_db", "pass_name": pass_name, "query": query})
        return {
            "chunks": [
                {"chunk_id": "good", "text": "Keep me", "score": 0.8, "source": "good.md", "review_status": "clean", "retrieval_allowed": True},
                {"chunk_id": "removed", "text": "Drop me", "score": 0.95, "source": "bad.md", "review_status": "removed", "retrieval_allowed": True},
                {"chunk_id": "blocked", "text": "Also drop me", "score": 0.7, "source": "blocked.md", "review_status": "clean", "retrieval_allowed": False},
            ]
        }

    backend.search_chunks = fake_search_chunks
    request = service.build_request({"question": "Filter chunks", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)

    asyncio.run(service.graph_runner.run(request, emitter))

    done_event = emitter.events[-1]
    source_ids = [chunk["chunk_id"] for chunk in done_event["data"]["sources"]]
    assert source_ids == ["good"]


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
