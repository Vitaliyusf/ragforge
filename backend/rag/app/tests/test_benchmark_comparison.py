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
        "build": {
            "git_sha": "abc123",
            "git_branch": "main",
            "build_timestamp": "2026-01-01T00:00:00Z",
            "image_tag": "rag:test",
        },
        "dataset": {"phases": phases or ["retrieval_base"]},
        "chunking": {"strategy": "fixed", "size": 500, "overlap": 50},
        "vector_store": {"type": "qdrant", "collection": "chunks"},
        "embedding": {"model": model, "vector_size": 768},
        "llm": {
            "implementation": "openai",
            "chat_model": "gpt-test",
            "max_model_len": 4096,
            "quantization": "none",
            "max_tokens": {
                "answer_generation": 128,
                "answer_evaluation": 512,
                "content_risk_scan": 128,
                "query_rewrite": 128,
                "memory_extraction": 512,
            },
        },
        "retrieval": {
            "top_k_documents": top_k,
            "eval_candidate_k": 50,
            "retrieval_strategy": "dense_vector",
            "context_k": top_k,
            "pass_two_active": True,
            "pass_two_chunk_threshold": 4,
            "pass_two_score_threshold": 0.5,
            "reranker_active": False,
            "hybrid_search_active": False,
        },
        "unobserved": [],
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
        "authoritative": True,
    }


def compatibility_field(result, name):
    return next(row for row in result["compatibility_fields"] if row["field"] == name)


def test_critical_fields_distinguish_same_different_and_unknown():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")
    same = benchmark_compatibility(baseline, candidate)
    assert compatibility_field(same, "embedding.model")["status"] == "same"
    assert same["compatibility_status"] == "compatible"

    candidate["manifest"]["embedding"]["model"] = "embed-v2"
    different = benchmark_compatibility(baseline, candidate)
    assert compatibility_field(different, "embedding.model")["status"] == "different"
    assert different["compatibility_status"] == "incompatible"


def test_known_token_budget_difference_is_incompatible():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")
    baseline["manifest"]["llm"]["max_tokens"]["answer_generation"] = 512

    result = benchmark_compatibility(baseline, candidate)

    assert compatibility_field(result, "llm.max_tokens")["status"] == "different"
    assert result["compatibility_status"] == "incompatible"


def test_missing_historical_token_budgets_make_compatibility_unknown():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")
    baseline["manifest"]["llm"].pop("max_tokens")

    result = benchmark_compatibility(baseline, candidate)

    assert compatibility_field(result, "llm.max_tokens")["status"] == "unknown"
    assert result["compatibility_status"] == "unknown"


@pytest.mark.parametrize("left,right", [(None, None), ("embed-v1", None)])
def test_null_critical_provenance_is_unknown(left, right):
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")
    baseline["manifest"]["embedding"]["model"] = left
    candidate["manifest"]["embedding"]["model"] = right
    result = benchmark_compatibility(baseline, candidate)
    assert compatibility_field(result, "embedding.model")["status"] == "unknown"
    assert result["compatibility_status"] == "unknown"
    assert result["compatible"] is False


def test_explicitly_unobserved_critical_value_is_unknown_even_when_present():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")
    baseline["manifest"]["unobserved"] = ["embedding.model"]
    result = benchmark_compatibility(baseline, candidate)
    assert compatibility_field(result, "embedding.model")["status"] == "unknown"
    assert result["compatibility_status"] == "unknown"


def test_noncritical_unknown_does_not_block_compatibility():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")
    baseline["manifest"]["software"] = {"platform": None}
    candidate["manifest"]["software"] = {"platform": None}
    baseline["manifest"]["unobserved"] = ["software.platform"]
    candidate["manifest"]["unobserved"] = ["software.platform"]
    assert (
        benchmark_compatibility(baseline, candidate)["compatibility_status"]
        == "compatible"
    )


def test_historical_manifest_schema_remains_readable_but_unknown():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")
    baseline["manifest"] = {
        "manifest_version": 1,
        "embedding": {"model": "embed-v1"},
        "retrieval": {"reranker_enabled": True},
    }

    result = benchmark_compatibility(baseline, candidate)

    assert result["compatible"] is False
    assert result["compatibility_status"] == "unknown"


def test_unknown_comparison_keeps_non_authoritative_metric_deltas():
    baseline = benchmark("base", created_at="2026-01-01", value=0.5)
    candidate = benchmark("candidate", created_at="2026-01-02", value=0.75)
    candidate["manifest"]["build"]["git_sha"] = None
    candidate["manifest"]["unobserved"] = ["build.git_sha"]
    comparison = compare_benchmarks(baseline, candidate)
    assert comparison["compatibility_status"] == "unknown"
    assert comparison["metrics_authoritative"] is False
    row = metric(comparison, "phases.retrieval_base.retrieval.mrr")
    assert row["absolute_delta"] == pytest.approx(0.25)
    assert row["authoritative"] is False


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
