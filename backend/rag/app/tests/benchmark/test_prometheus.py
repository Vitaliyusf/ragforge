"""The vLLM half of a benchmark's operational evidence.

RAGForge's own ``ragapp_llm_*`` series measure the client side of a generation.
They cannot say how many requests were queued behind it, how full the KV cache
was, or whether the prefix cache hit — only the server can, and only if someone
scrapes it. These tests defend the two properties that make that scrape usable
as evidence: it asks vLLM about vLLM, and a metric the running release does not
export comes back as absent rather than as zero.
"""
from __future__ import annotations

import re

import pytest

from app.services.benchmark_prometheus import (
    SNAPSHOT_QUERIES,
    NullBenchmarkPrometheusSnapshotter,
)

VLLM_QUERIES = SNAPSHOT_QUERIES["vllm"]


def test_the_snapshot_has_a_place_for_the_server_s_own_metrics():
    assert "vllm" in SNAPSHOT_QUERIES
    assert VLLM_QUERIES


@pytest.mark.parametrize("name", sorted(VLLM_QUERIES))
def test_every_vllm_query_asks_vllm(name):
    """A ragapp_ series here would silently re-measure the client side."""
    query = VLLM_QUERIES[name]
    assert "vllm:" in query or 'job="vllm"' in query
    assert "ragapp_" not in query


# Labels a snapshot may group by. Bounded by construction: one model is
# served, and finish reasons are a closed set.
GROUPABLE_LABELS = frozenset({"model_name", "finished_reason", "le", "job"})


@pytest.mark.parametrize("name", sorted(VLLM_QUERIES))
def test_no_vllm_query_groups_by_a_high_cardinality_label(name):
    """Benchmarks are evidence, not a place to fan a series out per request."""
    grouped = re.findall(r"by \(([^)]*)\)", VLLM_QUERIES[name])
    labels = {label.strip() for clause in grouped for label in clause.split(",")}
    assert labels <= GROUPABLE_LABELS, f"{name} groups by {labels - GROUPABLE_LABELS}"


def test_the_evidence_a_scheduler_comparison_needs_is_requested():
    """Each of these answers a question the decision thresholds ask."""
    for name in (
        "num_requests_running",
        "num_requests_waiting",
        "prefix_cache_hits_total",
        "prompt_token_rate",
        "generation_token_rate",
        "finish_reason_total",
        "ttft_p95",
        "inter_token_latency_p95",
    ):
        assert name in VLLM_QUERIES


def test_both_spellings_of_a_renamed_metric_are_asked_for():
    """Names moved between engine versions; the wrong guess reads as silence."""
    assert {"kv_cache_usage_perc", "gpu_cache_usage_perc"} <= set(VLLM_QUERIES)
    assert {"num_preemptions_total", "request_preemptions_total"} <= set(VLLM_QUERIES)


def test_scrape_health_is_recorded_alongside_the_metrics():
    """Without it, every empty result is ambiguous between two causes."""
    assert 'up{job="vllm"}' in VLLM_QUERIES["scrape_up"]


@pytest.mark.asyncio
async def test_an_unavailable_prometheus_reports_absence_not_zeros():
    snapshot = await NullBenchmarkPrometheusSnapshotter().capture()

    assert snapshot["prometheus_available"] is False
    # An empty section says "nothing was observed". A section of zeros would
    # claim the benchmark saw no queueing and no preemptions, which is the one
    # conclusion a failed scrape must never support.
    assert snapshot["sections"]["vllm"] == {}
