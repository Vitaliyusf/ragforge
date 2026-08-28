"""Checkpoint restore, async persistence and feedback/turn durability."""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from app.core.config import RAGConfig
from app.services.conversation_events import CollectingConversationEmitter
from app.services.conversation_persistence import (
    AsyncConversationPersistence,
    InMemoryConversationStore,
)
from app.services.conversation_types import build_initial_state
from app.tests._service_harness import (
    TEST_IDENTITY,
    build_service,
)


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


def _save_extended_checkpoint(store, request, stage: str, chunks: list[dict[str, Any]]) -> None:
    state = build_initial_state(request)
    state["retrieval_plan"] = {
        "rewritten_query": f"rewrite:{request.user_message}",
        "subqueries": ["subquery one"],
        "pass_two_hints": ["fallback query"],
    }
    state["retrieved_chunks"] = chunks
    store.save_checkpoint(
        {
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "request_id": request.request_id,
            "trace_id": request.trace_id,
            "node": "crashed_node",
            "stage": stage,
            "status": "ok",
            "state": state,
            "created_at": "2026-03-17T00:00:00Z",
        }
    )


def test_extended_resume_after_pass_one_runs_pass_two_then_final_ranking():
    service, backend, store = build_service()
    request = service.build_request(
        {"question": "Please do a second retrieval", "mode": "extended"}
    )
    _save_extended_checkpoint(
        store,
        request,
        "after_pass_one",
        [{"chunk_id": "c1", "text": "Pass one", "score": 0.31, "source": "one"}],
    )

    result = asyncio.run(
        service.graph_runner.run(request, CollectingConversationEmitter(request), resume=True)
    )

    retrieval_calls = [call for call in backend.calls if call["type"] == "vector_db"]
    assert [call["pass_name"] for call in retrieval_calls] == ["pass_two"]
    assert [chunk["chunk_id"] for chunk in result["sources"]] == ["c2", "c1"]
    assert any(item["stage"] == "after_final_ranking" for item in store.checkpoints)


def test_extended_resume_after_pass_two_runs_final_ranking_exactly_once():
    service, backend, store = build_service()
    request = service.build_request({"question": "Resume after pass two", "mode": "extended"})
    _save_extended_checkpoint(
        store,
        request,
        "after_pass_two",
        [
            {"chunk_id": "c1", "text": "Pass one", "score": 0.31, "source": "one"},
            {"chunk_id": "c2", "text": "Pass two", "score": 0.91, "source": "two"},
        ],
    )
    original_ranking = service.graph_runner._rerank_and_merge
    ranking_calls = 0

    async def count_ranking(state, runtime):
        nonlocal ranking_calls
        ranking_calls += 1
        return await original_ranking(state, runtime)

    service.graph_runner._rerank_and_merge = count_ranking

    result = asyncio.run(
        service.graph_runner.run(request, CollectingConversationEmitter(request), resume=True)
    )

    assert ranking_calls == 1
    assert not any(call["type"] == "vector_db" for call in backend.calls)
    assert [chunk["chunk_id"] for chunk in result["sources"]] == ["c2", "c1"]


def test_extended_resume_after_final_ranking_repeats_no_retrieval_work():
    service, backend, store = build_service()
    request = service.build_request({"question": "Resume after final ranking", "mode": "extended"})
    _save_extended_checkpoint(
        store,
        request,
        "after_final_ranking",
        [
            {"chunk_id": "c2", "text": "Pass two", "score": 0.91, "source": "two"},
            {"chunk_id": "c1", "text": "Pass one", "score": 0.31, "source": "one"},
        ],
    )
    ranking_calls = 0

    async def count_ranking(state, runtime):
        nonlocal ranking_calls
        ranking_calls += 1
        return {"retrieved_chunks": state["retrieved_chunks"]}

    service.graph_runner._rerank_and_merge = count_ranking

    result = asyncio.run(
        service.graph_runner.run(request, CollectingConversationEmitter(request), resume=True)
    )

    assert ranking_calls == 0
    assert not any(call["type"] == "vector_db" for call in backend.calls)
    assert [chunk["chunk_id"] for chunk in result["sources"]] == ["c2", "c1"]


def test_fresh_extended_run_persists_unambiguous_retrieval_milestones():
    service, _, store = build_service()
    request = service.build_request(
        {"question": "Please do a second retrieval", "mode": "extended"}
    )

    asyncio.run(service.graph_runner.run(request, CollectingConversationEmitter(request)))

    retrieval_stages = [
        item["stage"]
        for item in store.checkpoints
        if item["stage"] in {"after_pass_one", "after_pass_two", "after_final_ranking"}
    ]
    assert retrieval_stages == ["after_pass_one", "after_pass_two", "after_final_ranking"]



def test_async_persistence_is_non_blocking_and_concurrency_bounded():
    class DelayedStore(InMemoryConversationStore):
        def __init__(self):
            super().__init__(RAGConfig(conversation_store_type="in_memory"))
            self.active_calls = 0
            self.max_active_calls = 0
            self.call_lock = threading.Lock()

        def save_checkpoint(self, document: dict[str, Any]) -> None:
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


