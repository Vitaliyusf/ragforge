"""Tests for the rag-side metrics aggregation.

The store double records every pipeline it is handed and returns canned
rows. That covers both halves of what matters here: the exact shape of the
pipeline sent to MongoDB — in particular the tenant boundary in the first
``$match`` — and the response built from its results.

The in-memory ``MetricsFactStore`` is not used as the double: it is a plain
list with no aggregation engine, so running a real ``$group`` against it
would mean writing a miniature MongoDB.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from app.services.metrics_query import (
    METRICS_ACTION,
    SCORE_BOUNDARIES,
    SCORE_GAP_BOUNDARIES,
    MetricsAccessDenied,
    MetricsQueryService,
    MetricsWindowInvalid,
)
from shared.auth import AuthIdentity
from shared.context import bound_context

ADMIN = AuthIdentity(tenant_id="tenant-a", user_id="admin-a", role="admin", admin_id="admin-a")
USER = AuthIdentity(tenant_id="tenant-a", user_id="user-a", role="user", admin_id="admin-a")


class RecordingStore:
    """Record aggregation pipelines and replay canned rows."""

    def __init__(self, rows: Optional[Dict[Optional[str], List[Dict[str, Any]]]] = None) -> None:
        self.pipelines: List[Dict[str, Any]] = []
        self._rows = rows or {}

    def aggregate(self, pipeline, *, collection=None):
        self.pipelines.append({"collection": collection, "pipeline": pipeline})
        return self._rows.get(collection, [])

    @property
    def first_match(self) -> Dict[str, Any]:
        """The ``$match`` of the first stage of the first pipeline recorded."""
        return self.pipelines[0]["pipeline"][0]["$match"]


def build_service(rows=None) -> MetricsQueryService:
    """Build the service on a fake config, independent of any .env file."""
    config = SimpleNamespace(
        hallucination_groundedness_threshold=0.6,
        user_feedback_collection="user_feedback",
    )
    return MetricsQueryService(config, RecordingStore(rows))


# ── Tenant scoping ────────────────────────────────────────────────────────

@pytest.mark.parametrize("section", ["overview", "quality", "retrieval", "cost"])
def test_tenant_filter_is_in_the_first_match_stage(section):
    """Scoping must happen in MongoDB, never by filtering rows in Python."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        getattr(service, section)("24h")

    match = service.store.first_match
    assert match["tenant_id"] == "tenant-a"
    assert "$gte" in match["ts"]


def test_worst_turns_also_scopes_in_the_first_match_stage():
    """The worst-turn listing is the most sensitive read, so check it too."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        service.worst_turns("7d")

    assert service.store.first_match["tenant_id"] == "tenant-a"


def test_owner_boundary_is_deliberately_absent():
    """Admin metrics span every user in the tenant, so no owner_user_id pin.

    This is the difference from conversation_persistence._scope(), and it is
    the reason every method asserts is_admin first.
    """
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        service.overview("24h")

    match = service.store.first_match
    assert "owner_user_id" not in match
    assert "owner_admin_id" not in match


def test_another_tenant_cannot_be_requested():
    """A cross-tenant view is out of scope and must not be reachable by argument."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        with pytest.raises(MetricsAccessDenied):
            service.overview("24h", tenant_id="tenant-b")

    assert service.store.pipelines == []


def test_own_tenant_may_be_named_explicitly():
    """Passing your own tenant is redundant but not an error."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        service.overview("24h", tenant_id="tenant-a")

    assert service.store.first_match["tenant_id"] == "tenant-a"


# ── Authorization ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("section", ["overview", "quality", "retrieval", "cost", "worst_turns"])
def test_non_admin_identity_is_rejected(section):
    """Every section drops the per-user boundary, so every one is admin-only."""
    service = build_service()

    with bound_context(**USER.to_dict()):
        with pytest.raises(MetricsAccessDenied):
            getattr(service, section)("24h")

    assert service.store.pipelines == []


def test_absent_identity_is_rejected():
    """An unidentified caller has no tenant, so there is no safe answer."""
    service = build_service()

    with bound_context(tenant_id=None, user_id=None, role=None, admin_id=None):
        with pytest.raises(MetricsAccessDenied):
            service.overview("24h")

    assert service.store.pipelines == []


def test_handle_reports_refusal_instead_of_raising():
    """The RPC entry point turns a refusal into a failed reply, not a crash."""
    service = build_service()

    with bound_context(**USER.to_dict()):
        result = service.handle({"sections": ["overview"], "window": "24h"})

    assert "error" in result
    assert "Administrator" in result["error"]


# ── Window validation ─────────────────────────────────────────────────────

@pytest.mark.parametrize("window", ["5m", "1y", "24h ", "1h;drop"])
def test_invalid_window_is_rejected(window):
    """rag validates the window itself rather than trusting the gateway."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        with pytest.raises(MetricsWindowInvalid):
            service.overview(window)


@pytest.mark.parametrize("window", [None, ""])
def test_missing_window_falls_back_to_the_default(window):
    """An absent window is not an error; only an unknown one is.

    Safe because this value never reaches a query string: it only selects a
    timedelta from the allow-list table.
    """
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        service.overview(window)

    assert service.store.pipelines


@pytest.mark.parametrize("window", ["1h", "24h", "7d", "30d"])
def test_allowed_windows_are_accepted(window):
    """The four documented windows all run."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        service.overview(window)

    assert service.store.first_match["tenant_id"] == "tenant-a"


# ── Response shape ────────────────────────────────────────────────────────

def test_overview_shape_from_aggregation_rows():
    """Rates are derived from the aggregated counts, not recomputed later."""
    service = build_service(
        {
            None: [
                {
                    "turns": 20,
                    "errored_turns": 4,
                    "turns_with_chunks": 15,
                    "mean_latency_ms": 1200.0,
                    "mean_groundedness": 0.75,
                    "tokens_in": 900,
                    "tokens_out": 300,
                }
            ]
        }
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.overview("24h")

    assert result["turns"] == 20
    assert result["error_rate"] == pytest.approx(0.2)
    assert result["retrieval_hit_rate"] == pytest.approx(0.75)
    assert result["mean_groundedness"] == pytest.approx(0.75)
    assert result["tokens_in"] == 900


def test_rates_are_none_rather_than_zero_when_there_are_no_turns():
    """A rate over an empty window is unknown; 0.0 would read as healthy."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        result = service.overview("24h")

    assert result["turns"] == 0
    assert result["error_rate"] is None
    assert result["retrieval_hit_rate"] is None


def test_quality_keeps_the_proxy_metric_explicitly_named():
    """The coarse figure must never be exposed as a bare hallucination rate."""
    service = build_service(
        {
            None: [
                {
                    "totals": [{"turns": 10, "scored_turns": 8, "below_threshold": 2}],
                    "groundedness_histogram": [{"_id": 0.6, "count": 3}],
                    "confidence": [{"_id": "high", "count": 5}],
                }
            ]
        }
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.quality("24h")

    assert result["hallucination_rate_proxy_groundedness"] == pytest.approx(0.25)
    assert result["hallucination_groundedness_threshold"] == 0.6
    assert result["groundedness_histogram"] == [{"bucket": "0.6-0.8", "count": 3}]
    assert result["confidence_mix"] == [{"level": "high", "count": 5}]


def test_quality_reports_the_real_hallucination_rate_from_verdicts():
    """The claim-level rate divides by the turns that actually have a verdict."""
    service = build_service(
        {
            None: [
                {
                    "totals": [
                        {
                            "turns": 10,
                            "scored_turns": 10,
                            "below_threshold": 4,
                            "verdict_turns": 8,
                            "hallucinated_turns": 2,
                            "severe_turns": 1,
                            "mean_unsupported_claims": 0.5,
                            "unsupported_claim_turns": 8,
                        }
                    ],
                    "hallucination": [
                        {"_id": "none", "count": 6},
                        {"_id": "minor", "count": 1},
                        {"_id": "severe", "count": 1},
                    ],
                }
            ]
        }
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.quality("24h")

    assert result["hallucination_rate"] == pytest.approx(0.25)
    assert result["hallucination_severe_rate"] == pytest.approx(0.125)
    assert result["hallucination_verdict_turns"] == 8
    assert result["mean_unsupported_claims"] == 0.5
    assert result["hallucination_verdict_mix"] == [
        {"verdict": "none", "count": 6},
        {"verdict": "minor", "count": 1},
        {"verdict": "severe", "count": 1},
    ]


def test_quality_does_not_blend_a_window_spanning_the_phase_six_deploy():
    """Pre- and post-deploy turns are reported side by side, never merged.

    Ten turns: eight predate phase 6 and carry only a groundedness score,
    two were judged with claim-level verdicts (one of them hallucinating).
    The real rate is 1/2 over its own denominator; the proxy is 4/10 over
    all scored turns; neither is allowed to absorb the other's turns.
    """
    service = build_service(
        {
            None: [
                {
                    "totals": [
                        {
                            "turns": 10,
                            "scored_turns": 10,
                            "below_threshold": 4,
                            "verdict_turns": 2,
                            "hallucinated_turns": 1,
                            "severe_turns": 0,
                        }
                    ],
                    "hallucination": [
                        {"_id": "none", "count": 1},
                        {"_id": "minor", "count": 1},
                    ],
                }
            ]
        }
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.quality("24h")

    assert result["hallucination_rate"] == pytest.approx(0.5)
    assert result["hallucination_verdict_turns"] == 2
    assert result["turns_without_verdict"] == 8
    assert result["hallucination_rate_proxy_groundedness"] == pytest.approx(0.4)
    assert result["hallucination_rate"] != result["hallucination_rate_proxy_groundedness"]


def test_quality_reports_no_verdicts_as_unmeasured_not_zero():
    """A window entirely predating phase 6 has no real rate at all."""
    service = build_service(
        {
            None: [
                {
                    "totals": [
                        {"turns": 6, "scored_turns": 6, "below_threshold": 1, "verdict_turns": 0}
                    ]
                }
            ]
        }
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.quality("24h")

    assert result["hallucination_rate"] is None
    assert result["turns_without_verdict"] == 6
    assert result["hallucination_rate_proxy_groundedness"] is not None


def test_quality_reports_citation_means_with_their_denominators():
    """A mean is shown with the count it was taken over, and what it excluded."""
    service = build_service(
        {
            None: [
                {
                    "totals": [
                        {
                            "turns": 10,
                            "scored_turns": 10,
                            "citation_evaluated_turns": 10,
                            "citation_precision_turns": 4,
                            "mean_citation_precision": 0.5,
                            "citation_recall_turns": 5,
                            "mean_citation_recall": 1.0,
                            "mean_citation_count": 1.5,
                            "mean_cited_chunk_ratio": 0.25,
                            "cited_turns": 4,
                        }
                    ]
                }
            ]
        }
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.quality("24h")

    assert result["mean_citation_precision"] == 0.5
    assert result["citation_precision_turns"] == 4
    # Six answers cited nothing: excluded from precision, not scored 0.0.
    assert result["citation_precision_excluded"] == 6
    assert result["citation_recall_excluded"] == 5
    assert result["citation_f1"] == pytest.approx(2 / 3)


def test_quality_citation_f1_is_unmeasured_when_either_half_is():
    """Half a measurement is not a measurement."""
    service = build_service(
        {None: [{"totals": [{"turns": 3, "mean_citation_precision": 0.9}]}]}
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.quality("24h")

    assert result["mean_citation_recall"] is None
    assert result["citation_f1"] is None


def test_cost_returns_tokens_and_no_price():
    """Pricing lives only in the gateway, so rag must not emit a cost field."""
    service = build_service(
        {
            None: [
                {
                    "by_model": [
                        {"_id": "model-a", "turns": 3, "tokens_in": 100, "tokens_out": 50}
                    ],
                    "by_tenant": [
                        {"_id": "tenant-a", "turns": 3, "tokens_in": 100, "tokens_out": 50}
                    ],
                }
            ]
        }
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.cost("24h")

    assert result["by_model"] == [
        {"model": "model-a", "turns": 3, "tokens_in": 100, "tokens_out": 50}
    ]
    assert result["by_tenant"] == [
        {"tenant_id": "tenant-a", "turns": 3, "tokens_in": 100, "tokens_out": 50}
    ]
    assert result["tokens_in"] == 100
    assert not [key for key in result if "cost" in key or "usd" in key]


def test_worst_turns_projects_identifiers_and_scores_only():
    """No message or answer text may leave the service on this path."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        service.worst_turns("24h")

    project = service.store.pipelines[0]["pipeline"][-1]["$project"]
    assert set(project) == {
        "_id",
        "turn_id",
        "conversation_id",
        "ts",
        "groundedness",
        "completeness",
        "safety",
        "confidence",
        "unsupported_claim_count",
        "hallucination_verdict",
        "citation_precision",
    }
    # Counts and verdicts, never the claim text they were derived from.
    assert "claims" not in project


def test_worst_turns_sorts_ascending_and_caps_the_limit():
    """Worst means lowest groundedness, and the cap bounds the response size."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        service.worst_turns("24h", limit=5_000)

    stages = service.store.pipelines[0]["pipeline"]
    assert {"$sort": {"groundedness": 1, "unsupported_claim_count": -1}} in stages
    assert stages[2]["$limit"] == 50


def test_retrieval_reports_empty_and_hit_rates():
    """Hit rate and empty-retrieval rate are complementary views of the same count."""
    service = build_service(
        {
            None: [
                {
                    "totals": [
                        {
                            "turns": 10,
                            "turns_with_chunks": 7,
                            "empty_retrievals": 3,
                            "reranker_evaluated": 4,
                            "reranker_changed": 1,
                        }
                    ],
                    "top_score_histogram": [],
                    "chunks_per_query": [],
                }
            ]
        }
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.retrieval("24h")

    assert result["hit_rate"] == pytest.approx(0.7)
    assert result["empty_retrieval_rate"] == pytest.approx(0.3)
    assert result["reranker_changed_top1_rate"] == pytest.approx(0.25)


def test_retrieval_reports_the_score_gap_with_its_denominator():
    """The gap mean is meaningless without the count it was averaged over."""
    service = build_service(
        {
            None: [
                {
                    "totals": [{"turns": 10, "mean_score_gap": 0.42, "score_gap_turns": 6}],
                    "top_score_histogram": [],
                    "chunks_per_query": [],
                    "score_gap_histogram": [
                        {"_id": 0.0, "count": 2},
                        {"_id": 0.2, "count": 4},
                    ],
                }
            ]
        }
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.retrieval("24h")

    assert result["mean_score_gap"] == pytest.approx(0.42)
    # Smaller than `turns`: four turns returned under five chunks.
    assert result["score_gap_turns"] == 6
    assert result["turns"] == 10
    assert result["score_gap_histogram"] == [
        {"bucket": "0.0-0.05", "count": 2},
        {"bucket": "0.2-0.4", "count": 4},
    ]


def test_retrieval_over_an_empty_window_returns_none_not_zero():
    """A window with no turns must not raise, and must not invent a 0% rate.

    This is the division-by-zero case. `0.0` here would render as a confident
    "0% empty retrievals" on a tab that measured nothing at all.
    """
    service = build_service(
        {None: [{"totals": [], "top_score_histogram": [], "chunks_per_query": []}]}
    )

    with bound_context(**ADMIN.to_dict()):
        result = service.retrieval("24h")

    assert result["turns"] == 0
    assert result["hit_rate"] is None
    assert result["empty_retrieval_rate"] is None
    assert result["reranker_changed_top1_rate"] is None
    assert result["mean_score_gap"] is None
    assert result["score_gap_turns"] == 0
    assert result["score_gap_histogram"] == []


def test_score_gap_buckets_use_their_own_boundaries():
    """The gap facet must not reuse the 0-1 score edges — gaps cluster near 0."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        service.retrieval("24h")

    facets = service.store.pipelines[0]["pipeline"][1]["$facet"]
    assert facets["score_gap_histogram"][1]["$bucket"]["boundaries"] == SCORE_GAP_BOUNDARIES
    assert facets["top_score_histogram"][1]["$bucket"]["boundaries"] == SCORE_BOUNDARIES


# ── Dispatch ──────────────────────────────────────────────────────────────

def test_handle_runs_only_the_requested_sections():
    """One RPC per route means the caller picks its sections."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        result = service.handle({"sections": ["overview", "cost"], "window": "24h"})

    assert set(result) == {"tenant_id", "overview", "cost"}


def test_handle_echoes_the_tenant_actually_queried():
    """The gateway reports this verbatim, so it must be the real tenant."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        result = service.handle({"sections": ["overview"]})

    assert result["tenant_id"] == "tenant-a"


def test_handle_ignores_unknown_sections():
    """An unknown section name is dropped rather than crashing the reply."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        result = service.handle({"sections": ["overview", "not_a_section"]})

    assert set(result) == {"tenant_id", "overview"}


def test_metrics_action_matches_the_gateway_literal():
    """rag cannot import RagAction, so the shared literal is asserted here."""
    assert METRICS_ACTION == "get_metrics"
