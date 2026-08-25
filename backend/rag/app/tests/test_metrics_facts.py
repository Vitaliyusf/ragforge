"""Tests for the pure turn-fact builder behind the admin metrics tab."""
from __future__ import annotations

from typing import Any, Dict

import pytest

from app.services.conversation_types import ConversationRequest
from app.services.metrics_facts import build_turn_fact, confidence_level


QUALITY_FIELDS = (
    "ttft_ms",
    "top_score",
    "mean_score",
    "reranker_changed_top1",
    "groundedness",
    "completeness",
    "safety",
    "confidence",
    "citation_count",
    "cited_chunk_ratio",
    "guardrail_blocked",
    "revised",
    "model",
    "tokens_in",
    "tokens_out",
)


def _request(mode: str = "regular") -> ConversationRequest:
    return ConversationRequest(
        user_message="What is RAG?",
        mode=mode,
        conversation_id="conv-1",
        turn_id="turn-1",
        tenant_id="tenant-a",
        user_id="user-a",
    )


def _successful_result() -> Dict[str, Any]:
    return {
        "answer": "Regular answer",
        "sources": [
            {"chunk_id": "c1", "text": "first", "score": 0.9},
            {"chunk_id": "c2", "text": "second", "score": 0.5},
        ],
        "review": {
            "verdict": "pass",
            "groundedness_score": 0.92,
            "completeness_score": 0.88,
            "safety_score": 1.0,
            "revision_applied": False,
        },
    }


def _timings(**overrides: Any) -> Dict[str, Any]:
    timings: Dict[str, Any] = {
        "latency_ms": 1234.5,
        "ttft_ms": 210.0,
        "stage_ms": {"retrieve_chunks": 120.0, "generate_answer": 900.0},
        "reranker_changed_top1": True,
        "guardrail_blocked": False,
        "model": "fake-generator",
        "usage": {"input_tokens": 500, "output_tokens": 120},
        "error_class": None,
    }
    timings.update(overrides)
    return timings


def test_successful_turn_carries_every_measured_field():
    fact = build_turn_fact(_request(), _successful_result(), _timings())

    assert fact.turn_id == "turn-1"
    assert fact.conversation_id == "conv-1"
    assert fact.tenant_id == "tenant-a"
    assert fact.mode == "regular"
    assert fact.latency_ms == 1234.5
    assert fact.ttft_ms == 210.0
    assert fact.stage_ms == {"retrieve_chunks": 120.0, "generate_answer": 900.0}
    assert fact.chunk_count == 2
    assert fact.top_score == pytest.approx(0.9)
    assert fact.mean_score == pytest.approx(0.7)
    assert fact.reranker_changed_top1 is True
    assert fact.groundedness == pytest.approx(0.92)
    assert fact.completeness == pytest.approx(0.88)
    assert fact.safety == pytest.approx(1.0)
    assert fact.confidence == "high"
    assert fact.guardrail_blocked is False
    assert fact.revised is False
    assert fact.model == "fake-generator"
    assert fact.tokens_in == 500
    assert fact.tokens_out == 120
    assert fact.error_class is None


def test_citation_fields_stay_none_because_the_app_emits_no_citations():
    fact = build_turn_fact(_request(), _successful_result(), _timings())

    assert fact.citation_count is None
    assert fact.cited_chunk_ratio is None


def test_errored_turn_leaves_quality_fields_none_rather_than_zero():
    result = {"answer": "", "sources": [], "review": {}, "error": "generation failed"}
    timings = _timings(
        ttft_ms=None,
        stage_ms={},
        reranker_changed_top1=None,
        guardrail_blocked=None,
        model=None,
        usage=None,
        error_class="RuntimeError",
    )

    fact = build_turn_fact(_request(), result, timings)

    for field in QUALITY_FIELDS:
        assert getattr(fact, field) is None, f"{field} must be None on an errored turn"
    assert fact.error_class == "RuntimeError"
    # Error latency is still real and must not be lost.
    assert fact.latency_ms == 1234.5
    assert fact.chunk_count == 0


def test_turn_with_no_retrieved_chunks_has_no_scores():
    result = {
        "answer": "I could not find anything relevant.",
        "sources": [],
        "review": {
            "verdict": "pass",
            "groundedness_score": 0.4,
            "completeness_score": 0.3,
            "safety_score": 1.0,
            "revision_applied": False,
        },
    }

    fact = build_turn_fact(_request(), result, _timings())

    assert fact.chunk_count == 0
    assert fact.top_score is None
    assert fact.mean_score is None
    # The evaluation still happened, so its scores are real.
    assert fact.groundedness == pytest.approx(0.4)
    assert fact.confidence == "low"


def test_chunks_without_scores_do_not_become_zero():
    result = {
        "answer": "Answer",
        "sources": [{"chunk_id": "c1", "text": "first"}],
        "review": {},
    }

    fact = build_turn_fact(_request(), result, _timings())

    assert fact.chunk_count == 1
    assert fact.top_score is None
    assert fact.mean_score is None


@pytest.mark.parametrize(
    "groundedness,expected",
    [(None, None), (0.95, "high"), (0.8, "high"), (0.6, "medium"), (0.5, "medium"), (0.2, "low")],
)
def test_confidence_level_buckets(groundedness, expected):
    assert confidence_level(groundedness) == expected
