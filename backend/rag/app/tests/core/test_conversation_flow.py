"""Regular and extended turn flow: streaming, revision, context reuse, failure semantics."""
from __future__ import annotations

import asyncio

import pytest
from shared.auth import AuthError
from shared.context import bound_context

from app.services.context_assembler import context_token_count
from app.services.conversation_events import CollectingConversationEmitter
from app.services.conversation_messages import (
    chunk_passages,
)
from app.services.conversation_types import build_initial_state
from app.services.retrieval_trace import RetrievalTrace
from app.tests._service_harness import (
    RecordingLogger,
    build_service,
)


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



def test_regular_generation_and_evaluation_share_assembled_passage_order():
    service, backend, _ = build_service()

    async def search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        return {
            "chunks": [
                {"chunk_id": "a1", "text": "highest", "score": 0.90, "source": "a.md"},
                {"chunk_id": "a2", "text": "same source", "score": 0.87, "source": "a.md"},
                {"chunk_id": "b1", "text": "diverse source", "score": 0.85, "source": "b.md"},
            ]
        }

    backend.search_chunks = search_chunks
    request = service.build_request({"question": "assemble regular context", "mode": "regular"})

    result = asyncio.run(
        service.graph_runner.run(request, CollectingConversationEmitter(request))
    )

    generation = next(call for call in backend.calls if call.get("request_type") == "answer_generation")
    evaluation = next(call for call in backend.calls if call.get("request_type") == "answer_evaluation")
    expected_ids = ["a1", "b1", "a2"]
    assert [item["chunk_id"] for item in result["sources"]] == expected_ids
    assert [item["source_id"] for item in generation["retrieved_context"]] == expected_ids
    assert generation["retrieved_context"] == chunk_passages(evaluation["retrieved_chunks"])



def test_context_budget_preserves_question_and_system_prompt_space():
    service, _, _ = build_service()
    service.graph_runner.config.generation_input_token_budget = 50
    service.graph_runner.config.generation_system_prompt_reserve_tokens = 40
    service.graph_runner.config.context_token_budget = 100
    request = service.build_request({"question": "a deliberately long user question"})
    state = build_initial_state(request)
    state["retrieved_chunks"] = [
        {"chunk_id": "c1", "text": "evidence", "score": 0.9, "source": "a.md"}
    ]

    selected = service.graph_runner._assemble_generation_context(
        state, request, "regular"
    )

    assert selected == []



def test_input_budget_accounts_for_both_context_prompt_representations():
    service, _, _ = build_service()
    service.graph_runner.config.generation_input_token_budget = 120
    service.graph_runner.config.generation_system_prompt_reserve_tokens = 0
    service.graph_runner.config.context_token_budget = 120
    request = service.build_request({"question": "budget context"})
    state = build_initial_state(request)
    state["retrieved_chunks"] = [
        {"chunk_id": "c1", "text": "evidence " * 100, "score": 0.9, "source": "a.md"}
    ]

    selected = service.graph_runner._assemble_generation_context(
        state, request, "regular"
    )

    assert selected
    assert 2 * context_token_count(selected) <= 120



def test_extended_generation_revision_and_evaluation_reuse_one_assembled_context():
    service, backend, _ = build_service()

    async def rewrite(request, context):
        return {"rewritten_query": "extended", "subqueries": [], "pass_two_hints": []}

    async def search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        assert pass_name == "pass_one"
        return {
            "chunks": [
                {"chunk_id": "a1", "text": "highest", "score": 0.90, "source": "a.md"},
                {"chunk_id": "a2", "text": "same source", "score": 0.87, "source": "a.md"},
                {"chunk_id": "b1", "text": "diverse source", "score": 0.85, "source": "b.md"},
            ]
        }

    backend.query_rewrite = rewrite
    backend.search_chunks = search_chunks
    request = service.build_request({"question": "assemble extended context", "mode": "extended"})

    result = asyncio.run(
        service.graph_runner.run(request, CollectingConversationEmitter(request))
    )

    generations = [call for call in backend.calls if call.get("request_type") == "answer_generation"]
    evaluation = next(call for call in backend.calls if call.get("request_type") == "answer_evaluation")
    expected = chunk_passages(evaluation["retrieved_chunks"])
    assert [item["chunk_id"] for item in result["sources"]] == ["a1", "b1", "a2"]
    assert len(generations) == 2
    assert all(call["retrieved_context"] == expected for call in generations)



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
    emitter = CollectingConversationEmitter(request)
    result = asyncio.run(service.graph_runner.run(request, emitter))

    assert result["outcome"] == "guardrail_blocked"
    assert result["guardrail_stage"] == "output"
    assert not any(event["type"] == "token" for event in emitter.events)
    assert emitter.ttft_seconds is None
    assert emitter.events[-1]["data"]["final_answer"] == "Safe response"


def test_approved_output_streams_only_after_the_output_guardrail():
    service, _, _ = build_service()
    request = service.build_request({"question": "What is RAG?", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)

    asyncio.run(service.graph_runner.run(request, emitter))

    token_indexes = [
        index for index, event in enumerate(emitter.events) if event["type"] == "token"
    ]
    guardrail_index = next(
        index
        for index, event in enumerate(emitter.events)
        if event["type"] == "status"
        and event["data"].get("node") == "output_guardrails"
        and event["data"].get("phase") == "started"
    )
    assert token_indexes
    assert min(token_indexes) > guardrail_index
    assert "".join(emitter.events[index]["data"]["text_delta"] for index in token_indexes).rstrip() == "Regular answer"


def test_extended_revision_never_streams_the_superseded_draft():
    service, _, _ = build_service()
    request = service.build_request(
        {"question": "Need second retrieval and revise this answer", "mode": "extended"}
    )
    emitter = CollectingConversationEmitter(request)

    asyncio.run(service.graph_runner.run(request, emitter))

    streamed = "".join(
        event["data"]["text_delta"]
        for event in emitter.events
        if event["type"] == "token"
    )
    assert streamed.rstrip() == "Revised final answer"
    assert "Draft answer" not in streamed


