"""Tests that the conversation graph actually moves its Prometheus series."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.services.conversation_events import CollectingConversationEmitter
from app.tests._service_harness import TEST_IDENTITY, build_service
from shared.context import bound_context
from shared.metrics import METRICS

# The assertions below read Prometheus internals, which only exist when the
# client library is installed. The no-op fallback is covered in
# backend/shared/tests/test_metrics_hooks.py.
pytest.importorskip("prometheus_client")


@pytest.fixture(autouse=True)
def authenticated_request_context():
    """Run the graph behind the same trusted identity boundary as runtime."""
    with bound_context(**TEST_IDENTITY.to_dict()):
        yield


def counter_value(metric: Any, **labels: str) -> float:
    """Current value of a labelled counter."""
    return metric.labels(**labels)._value.get()


def histogram_count(metric: Any, **labels: str) -> float:
    """Number of observations recorded on a labelled histogram.

    `observe()` increments only the first matching bucket — buckets are made
    cumulative at collection time — so the total is the sum across them.
    """
    return sum(bucket.get() for bucket in metric.labels(**labels)._buckets)


def run_turn(question: str, mode: str, fail_generation: bool = False):
    service, backend, _ = build_service()
    backend.fail_generation = fail_generation
    request = service.build_request({"question": question, "mode": mode})
    emitter = CollectingConversationEmitter(request)
    result = asyncio.run(service.graph_runner.run(request, emitter))
    return service, result, emitter


def test_successful_turn_moves_query_counters():
    before_total = counter_value(
        METRICS.rag_queries_total, service="rag", answer_mode="regular", status="success"
    )
    before_duration = histogram_count(
        METRICS.rag_query_duration, service="rag", answer_mode="regular"
    )
    before_sources = histogram_count(METRICS.rag_sources_per_query, service="rag")
    before_confidence = counter_value(
        METRICS.rag_confidence_level, service="rag", level="high"
    )

    _, result, _ = run_turn("What is RAG?", "regular")

    assert result["answer"] == "Regular answer"
    assert (
        counter_value(
            METRICS.rag_queries_total, service="rag", answer_mode="regular", status="success"
        )
        == before_total + 1
    )
    assert (
        histogram_count(METRICS.rag_query_duration, service="rag", answer_mode="regular")
        == before_duration + 1
    )
    assert histogram_count(METRICS.rag_sources_per_query, service="rag") == before_sources + 1
    # The fake evaluator returns groundedness 0.92, which buckets to "high".
    assert (
        counter_value(METRICS.rag_confidence_level, service="rag", level="high")
        == before_confidence + 1
    )


def test_errored_turn_records_error_status_and_its_latency():
    before_errors = counter_value(
        METRICS.rag_queries_total, service="rag", answer_mode="regular", status="error"
    )
    before_duration = histogram_count(
        METRICS.rag_query_duration, service="rag", answer_mode="regular"
    )

    _, result, _ = run_turn("What is RAG?", "regular", fail_generation=True)

    assert result["error"]
    assert (
        counter_value(
            METRICS.rag_queries_total, service="rag", answer_mode="regular", status="error"
        )
        == before_errors + 1
    )
    # Error latency must not be invisible.
    assert (
        histogram_count(METRICS.rag_query_duration, service="rag", answer_mode="regular")
        == before_duration + 1
    )


def test_retrieval_score_is_observed_once_per_turn_not_once_per_chunk():
    before = histogram_count(METRICS.rag_retrieval_score, service="rag")

    _, result, _ = run_turn("Needs a second retrieval", "extended")

    assert len(result["sources"]) > 1, "this test is only meaningful with several chunks"
    assert histogram_count(METRICS.rag_retrieval_score, service="rag") == before + 1


def test_stage_durations_are_recorded_under_normalized_stage_names():
    before_generate = histogram_count(
        METRICS.rag_stage_duration, service="rag", stage="generate_answer"
    )
    before_retrieve = histogram_count(
        METRICS.rag_stage_duration, service="rag", stage="retrieve_chunks"
    )

    run_turn("What is RAG?", "regular")

    assert (
        histogram_count(METRICS.rag_stage_duration, service="rag", stage="generate_answer")
        == before_generate + 1
    )
    assert (
        histogram_count(METRICS.rag_stage_duration, service="rag", stage="retrieve_chunks")
        == before_retrieve + 1
    )


def test_ttft_is_recorded_exactly_once_per_turn():
    before = histogram_count(METRICS.rag_ttft_seconds, service="rag", answer_mode="regular")

    _, _, emitter = run_turn("What is RAG?", "regular")

    token_events = [event for event in emitter.events if event["type"] == "token"]
    assert len(token_events) > 1, "the fake generator should stream several tokens"
    assert (
        histogram_count(METRICS.rag_ttft_seconds, service="rag", answer_mode="regular")
        == before + 1
    )
    assert emitter.ttft_seconds is not None


def test_ttft_is_recorded_for_non_admin_users():
    service, backend, _ = build_service()
    request = service.build_request({"question": "What is RAG?", "mode": "regular"})
    request.role = "user"
    emitter = CollectingConversationEmitter(request)
    before = histogram_count(METRICS.rag_ttft_seconds, service="rag", answer_mode="regular")

    asyncio.run(service.graph_runner.run(request, emitter))

    assert not any(event["type"] == "trace" for event in emitter.events)
    assert (
        histogram_count(METRICS.rag_ttft_seconds, service="rag", answer_mode="regular")
        == before + 1
    )


def test_disabled_reranker_does_not_invent_a_top1_change_measurement():
    before_true = counter_value(
        METRICS.rag_reranker_changed_top1, service="rag", changed="true"
    )

    run_turn("Needs a second retrieval", "extended")

    # Global Pass1 + Pass2 ranking promotes Pass2's higher-scoring chunk.
    assert (
        counter_value(METRICS.rag_reranker_changed_top1, service="rag", changed="true")
        == before_true
    )



def test_successful_turn_writes_one_turn_fact():
    service, result, _ = run_turn("What is RAG?", "regular")

    facts = service.graph_runner.metrics_facts.facts
    assert len(facts) == 1
    fact = facts[0]
    assert fact["mode"] == "regular"
    assert fact["tenant_id"] == TEST_IDENTITY.tenant_id
    assert fact["chunk_count"] == len(result["sources"])
    assert fact["latency_ms"] > 0
    assert fact["ttft_ms"] is not None
    assert fact["confidence"] == "high"
    assert fact["error_class"] is None
    # Every stage the turn ran through is present. The values can round to 0.0
    # here because the test doubles return instantly.
    assert set(fact["stage_ms"]) >= {"retrieve_chunks", "generate_answer", "evaluate_answer"}
    assert all(elapsed >= 0 for elapsed in fact["stage_ms"].values())
    assert fact["citation_count"] is None


def test_errored_turn_still_writes_a_fact_without_quality_scores():
    service, _, _ = run_turn("What is RAG?", "regular", fail_generation=True)

    facts = service.graph_runner.metrics_facts.facts
    assert len(facts) == 1
    fact = facts[0]
    assert fact["error_class"] == "RuntimeError"
    assert fact["groundedness"] is None
    assert fact["top_score"] is None
    assert fact["confidence"] is None
    assert fact["latency_ms"] > 0


def test_a_failing_metrics_write_never_fails_the_turn():
    service, backend, _ = build_service()

    class ExplodingStore:
        def save_fact(self, fact: Any) -> None:
            raise RuntimeError("mongo is down")

    service.graph_runner.metrics_facts = ExplodingStore()
    request = service.build_request({"question": "What is RAG?", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)

    result = asyncio.run(service.graph_runner.run(request, emitter))

    assert result["answer"] == "Regular answer"
    assert "error" not in result


# ── Citations and hallucination verdicts ──────────────────────────────────

def run_cited_turn(citations, claims, verdict="minor"):
    """Run one regular turn whose generator cites and whose judge decomposes.

    The doubles stand in for llm_agent, which is where citation extraction
    and claim analysis really happen; what is under test here is that the
    graph joins the two into per-turn figures and records them.
    """
    service, backend, _ = build_service()
    original_generate = backend.generate_answer
    original_evaluate = backend.evaluate_answer

    async def generate_answer(request, prompt, stream_request_id, token_callback):
        response = await original_generate(request, prompt, stream_request_id, token_callback)
        return {**response, "citations": citations, "invalid_citation_count": 0}

    async def evaluate_answer(request, answer, retrieved_chunks, mode):
        review = await original_evaluate(request, answer, retrieved_chunks, mode)
        return {**review, "claims": claims, "hallucination_verdict": verdict}

    backend.generate_answer = generate_answer
    backend.evaluate_answer = evaluate_answer

    request = service.build_request({"question": "What is RAG?", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)
    result = asyncio.run(service.graph_runner.run(request, emitter))
    return service, result, emitter


def test_a_cited_turn_records_its_citation_figures_in_the_fact():
    service, result, _ = run_cited_turn(
        citations=[{"source_id": "c1", "locator": "[1]", "snippet": "Regular chunk"}],
        # The judge answers in passage numbers; the graph resolves them to
        # chunk ids before anything is compared.
        claims=[{"claim": "RAG retrieves", "supported": True, "supporting_passage_ids": ["1"]}],
    )

    fact = service.graph_runner.metrics_facts.facts[0]
    assert fact["citation_count"] == 1
    assert fact["cited_chunk_ratio"] == 1.0
    assert fact["citation_precision"] == 1.0
    assert fact["citation_recall"] == 1.0
    assert fact["unsupported_claim_count"] == 0
    assert fact["hallucination_verdict"] == "minor"
    assert result["citations"][0]["source_id"] == "c1"




def test_the_hallucination_verdict_moves_its_counter():
    before = counter_value(METRICS.rag_hallucination_total, service="rag", verdict="severe")

    run_cited_turn(
        citations=[{"source_id": "c1"}],
        claims=[{"claim": "RAG invents", "supported": False, "supporting_passage_ids": []}],
        verdict="severe",
    )

    assert (
        counter_value(METRICS.rag_hallucination_total, service="rag", verdict="severe")
        == before + 1
    )


def test_citation_precision_is_observed_only_when_it_was_measured():
    before = histogram_count(METRICS.rag_citation_precision, service="rag")

    # An uncited answer: nothing to observe, and a 0.0 would be a lie.
    run_cited_turn(citations=[], claims=[])
    assert histogram_count(METRICS.rag_citation_precision, service="rag") == before

    run_cited_turn(
        citations=[{"source_id": "c1"}],
        claims=[{"claim": "RAG retrieves", "supported": True, "supporting_passage_ids": ["1"]}],
    )
    assert histogram_count(METRICS.rag_citation_precision, service="rag") == before + 1


def test_an_eval_run_turn_writes_no_fact_and_moves_no_counter():
    """`record_metrics=False` keeps synthetic turns out of the live numbers."""
    service, backend, _ = build_service()
    before = counter_value(
        METRICS.rag_queries_total, service="rag", answer_mode="regular", status="success"
    )
    request = service.build_request({"question": "What is RAG?", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)

    result = asyncio.run(
        service.graph_runner.run(request, emitter, record_metrics=False)
    )

    assert result["answer"] == "Regular answer"
    assert service.graph_runner.metrics_facts.facts == []
    assert (
        counter_value(
            METRICS.rag_queries_total, service="rag", answer_mode="regular", status="success"
        )
        == before
    )
