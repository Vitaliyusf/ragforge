"""Acceptance coverage for compatible and incompatible benchmark comparisons."""
from __future__ import annotations

import pytest

from app.services.benchmark_comparison import (
    benchmark_compatibility,
    compare_benchmarks,
    find_compatible_baseline,
)


def manifest(*, model="embed-v1", top_k=10, phases=None):
    return {
        "dataset": {"phases": phases or ["retrieval_base"]},
        "chunking": {"strategy": "fixed", "size": 500, "overlap": 50},
        "vector_store": {"type": "qdrant", "collection": "chunks"},
        "embedding": {"model": model, "vector_size": 768},
        "llm": {
            "implementation": "openai",
            "chat_model": "gpt-test",
            "max_model_len": 4096,
        },
        "retrieval": {"top_k_documents": top_k, "reranker_enabled": False},
    }


def benchmark(identifier, *, created_at, value=0.5, manifest_value=None, sha="abc"):
    return {
        "benchmark_id": identifier,
        "created_at": created_at,
        "status": "completed",
        "dataset_id": "dataset-1",
        "dataset_version": 1,
        "dataset_sha256": sha,
        "manifest": manifest_value or manifest(),
        "phases": [{
            "name": "retrieval_base", "status": "completed", "results": {
                "mrr": value,
                "recall_at_k": {"5": value},
                "mean_latency_ms": 10.0,
                "items_evaluated": 1,
            },
        }],
    }


def metric(comparison, name):
    return next(row for row in comparison["metrics"] if row["metric"] == name)


def test_compatible_runs_report_baseline_candidate_and_deltas():
    baseline = benchmark("base", created_at="2026-01-01", value=0.5)
    candidate = benchmark("candidate", created_at="2026-01-02", value=0.75)

    comparison = compare_benchmarks(baseline, candidate)
    row = metric(comparison, "phases.retrieval_base.retrieval.mrr")

    assert comparison["compatible"] is True
    assert comparison["warnings"] == []
    assert row == {
        "metric": "phases.retrieval_base.retrieval.mrr",
        "baseline": pytest.approx(0.5),
        "candidate": pytest.approx(0.75),
        "absolute_delta": pytest.approx(0.25),
        "percentage_delta": pytest.approx(50.0),
    }


def test_mismatch_categories_are_explicit_and_not_selected_as_a_baseline():
    candidate = benchmark("candidate", created_at="2026-01-03")
    wrong_dataset = benchmark("dataset", created_at="2026-01-02", sha="different")
    wrong_model = benchmark(
        "model", created_at="2026-01-01", manifest_value=manifest(model="embed-v2")
    )

    compatibility = benchmark_compatibility(wrong_model, candidate)

    assert compatibility["compatible"] is False
    assert {warning["category"] for warning in compatibility["warnings"]} == {"model"}
    assert (
        find_compatible_baseline(candidate, [candidate, wrong_dataset, wrong_model])
        is None
    )


def test_missing_and_zero_baseline_values_never_fabricate_percentage_changes():
    baseline = benchmark("base", created_at="2026-01-01", value=0.0)
    candidate = benchmark("candidate", created_at="2026-01-02", value=0.5)
    candidate["phases"][0]["results"].pop("mean_latency_ms")

    comparison = compare_benchmarks(baseline, candidate)

    assert (
        metric(comparison, "phases.retrieval_base.retrieval.mrr")[
            "percentage_delta"
        ]
        is None
    )
    latency = metric(comparison, "phases.retrieval_base.latency_ms.mean")
    assert latency["candidate"] is None
    assert latency["absolute_delta"] is None
