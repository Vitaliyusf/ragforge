"""Acceptance coverage for compatible and incompatible benchmark comparisons."""
from __future__ import annotations

import pytest

from app.services.benchmark_comparison import (
    benchmark_compatibility,
    compare_benchmarks,
    find_compatible_baseline,
)


# One benchmark's judge contract: the digest of the JSON Schema the evaluator
# was held to, and the prompt version that told it how to fill the schema in.
SCHEMA_SHA = "0a82f6655e9b44131b110fa343dd64cd98de79b1e7fd407b59b8591d53654e92"
# The same schema with `claims` unbounded hashes differently — that is the
# whole point of recording it.
UNBOUNDED_SCHEMA_SHA = "b3" + SCHEMA_SHA[2:]


def manifest(
    *,
    model="embed-v1",
    top_k=10,
    phases=None,
    vllm_version="0.28.0",
    vllm_image="vllm/vllm-openai:v0.28.0",
    vllm_overrides=None,
    answer_evaluation_transport="legacy",
    answer_evaluation_schema_sha=SCHEMA_SHA,
    answer_evaluation_prompt_version="answer_evaluation.v2",
):
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
            "structured_output_transport": {
                "answer_evaluation": answer_evaluation_transport
            },
            "output_schema_sha256": {"answer_evaluation": answer_evaluation_schema_sha},
            "prompt_version": {"answer_evaluation": answer_evaluation_prompt_version},
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
        "vllm": {
            "image": vllm_image,
            "server_version": vllm_version,
            "model_runner": "v1",
            "max_model_len": 4096,
            "max_num_seqs": 4,
            "gpu_memory_utilization": 0.8,
            "quantization": "none",
            "prefix_caching": True,
            # Recorded nulls: RAGForge passes no scheduler flag, and the
            # manifest says so rather than omitting the knob.
            "max_num_batched_tokens": None,
            "performance_mode": None,
            "async_scheduling": None,
            "chunked_prefill": None,
            "scheduler_reserve_full_isl": None,
            **(vllm_overrides or {}),
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


# ── vLLM runtime provenance ─────────────────────────────────


def test_identical_unset_vllm_scheduler_knobs_stay_compatible():
    """A knob neither run configured must not make them incomparable."""
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    assert (
        compatibility_field(result, "vllm.max_num_batched_tokens")["status"] == "same"
    )
    assert compatibility_field(result, "vllm.performance_mode")["status"] == "same"
    assert result["compatibility_status"] == "compatible"


def test_vllm_version_upgrade_is_incompatible_not_unknown():
    """The whole point of the upgrade experiment: 0.27.1 != 0.28.0."""
    baseline = benchmark(
        "base",
        created_at="2026-01-01",
        manifest_value=manifest(
            vllm_version="0.27.1", vllm_image="vllm/vllm-openai:v0.27.1"
        ),
    )
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    assert compatibility_field(result, "vllm.server_version")["status"] == "different"
    assert compatibility_field(result, "vllm.image")["status"] == "different"
    assert result["compatibility_status"] == "incompatible"


def test_version_incompatible_runs_still_report_their_metrics():
    """Incompatible only demotes authority; it must not hide the numbers."""
    baseline = benchmark(
        "base",
        created_at="2026-01-01",
        value=0.5,
        manifest_value=manifest(
            vllm_version="0.27.1", vllm_image="vllm/vllm-openai:v0.27.1"
        ),
    )
    candidate = benchmark("candidate", created_at="2026-01-02", value=0.75)

    comparison = compare_benchmarks(baseline, candidate)
    row = metric(comparison, "phases.retrieval_base.retrieval.mrr")

    assert comparison["compatibility_status"] == "incompatible"
    assert comparison["metrics_authoritative"] is False
    assert row["baseline"] == pytest.approx(0.5)
    assert row["candidate"] == pytest.approx(0.75)
    assert row["percentage_delta"] == pytest.approx(50.0)


def test_tuned_scheduler_knob_differs_from_the_unset_reference():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark(
        "candidate",
        created_at="2026-01-02",
        manifest_value=manifest(vllm_overrides={"max_num_batched_tokens": 8192}),
    )

    result = benchmark_compatibility(baseline, candidate)

    assert (
        compatibility_field(result, "vllm.max_num_batched_tokens")["status"]
        == "different"
    )
    assert result["compatibility_status"] == "incompatible"


def test_model_runner_change_is_incompatible():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark(
        "candidate",
        created_at="2026-01-02",
        manifest_value=manifest(vllm_overrides={"model_runner": "v2"}),
    )

    result = benchmark_compatibility(baseline, candidate)

    assert compatibility_field(result, "vllm.model_runner")["status"] == "different"


def test_answer_evaluation_transport_change_is_incompatible():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark(
        "candidate",
        created_at="2026-01-02",
        manifest_value=manifest(answer_evaluation_transport="json_schema"),
    )

    result = benchmark_compatibility(baseline, candidate)

    assert compatibility_field(
        result, "llm.structured_output_transport.answer_evaluation"
    )["status"] == "different"
    assert result["compatibility_status"] == "incompatible"


def test_historical_manifest_without_transport_remains_readable_as_unknown():
    legacy = manifest()
    legacy["llm"].pop("structured_output_transport")
    baseline = benchmark("base", created_at="2026-01-01", manifest_value=legacy)
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    assert compatibility_field(
        result, "llm.structured_output_transport.answer_evaluation"
    )["status"] == "unknown"


def test_manifest_without_a_vllm_section_reads_as_unknown():
    """Runs recorded before manifest v6 must stay readable and conservative."""
    legacy = manifest()
    del legacy["vllm"]
    baseline = benchmark("base", created_at="2026-01-01", manifest_value=legacy)
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    assert (
        compatibility_field(result, "vllm.server_version")["status"] == "unknown"
    )
    assert (
        compatibility_field(result, "vllm.max_num_batched_tokens")["status"]
        == "unknown"
    )
    assert result["compatibility_status"] == "unknown"


def test_unobserved_vllm_version_is_never_treated_as_agreement():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")
    candidate["manifest"]["vllm"]["server_version"] = None
    candidate["manifest"]["unobserved"] = ["vllm.server_version"]

    result = benchmark_compatibility(baseline, candidate)

    assert compatibility_field(result, "vllm.server_version")["status"] == "unknown"


# ── Judge-contract compatibility (GEN-03G) ────────────────────────────────

def test_identical_judge_contracts_compare_as_same():
    baseline = benchmark("base", created_at="2026-01-01")
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    for field in (
        "llm.output_schema_sha256.answer_evaluation",
        "llm.prompt_version.answer_evaluation",
    ):
        assert compatibility_field(result, field)["status"] == "same"
    assert result["compatibility_status"] == "compatible"


def test_output_schema_difference_is_incompatible():
    """The GEN-03F claims cap changed what the quality metrics measure."""
    baseline = benchmark(
        "base",
        created_at="2026-01-01",
        manifest_value=manifest(answer_evaluation_schema_sha=UNBOUNDED_SCHEMA_SHA),
    )
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    row = compatibility_field(result, "llm.output_schema_sha256.answer_evaluation")
    assert row["status"] == "different"
    assert row["baseline"] == UNBOUNDED_SCHEMA_SHA
    assert row["candidate"] == SCHEMA_SHA
    assert result["compatibility_status"] == "incompatible"


def test_prompt_version_difference_is_incompatible():
    baseline = benchmark(
        "base",
        created_at="2026-01-01",
        manifest_value=manifest(answer_evaluation_prompt_version="answer_evaluation.v1"),
    )
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    assert compatibility_field(
        result, "llm.prompt_version.answer_evaluation"
    )["status"] == "different"
    assert result["compatibility_status"] == "incompatible"


def test_incompatible_judge_contracts_still_report_their_metrics():
    """Incompatible is a verdict on comparability, not a refusal to report."""
    baseline = benchmark(
        "base",
        created_at="2026-01-01",
        value=0.5,
        manifest_value=manifest(answer_evaluation_schema_sha=UNBOUNDED_SCHEMA_SHA),
    )
    candidate = benchmark("candidate", created_at="2026-01-02", value=0.75)

    comparison = compare_benchmarks(baseline, candidate)
    row = metric(comparison, "phases.retrieval_base.retrieval.mrr")

    assert comparison["compatible"] is False
    assert row["baseline"] == pytest.approx(0.5)
    assert row["candidate"] == pytest.approx(0.75)
    assert row["authoritative"] is False


@pytest.mark.parametrize(
    "missing",
    ["output_schema_sha256", "prompt_version"],
)
def test_historical_manifest_without_judge_contract_is_unknown_not_same(missing):
    """Readable, but it cannot prove the judge contract either way."""
    legacy = manifest()
    legacy["llm"].pop(missing)
    baseline = benchmark("base", created_at="2026-01-01", manifest_value=legacy)
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    row = compatibility_field(result, f"llm.{missing}.answer_evaluation")
    assert row["status"] == "unknown"
    assert row["baseline"] is None
    assert result["compatibility_status"] != "compatible"


@pytest.mark.parametrize(
    "field,value",
    [
        ("answer_evaluation_schema_sha", None),
        ("answer_evaluation_prompt_version", None),
    ],
)
def test_null_judge_contract_provenance_is_unknown(field, value):
    baseline = benchmark(
        "base", created_at="2026-01-01", manifest_value=manifest(**{field: value})
    )
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    assert result["compatibility_status"] != "compatible"


def test_unobserved_judge_contract_is_never_treated_as_agreement():
    legacy = manifest()
    legacy["unobserved"] = ["llm.output_schema_sha256.answer_evaluation"]
    baseline = benchmark("base", created_at="2026-01-01", manifest_value=legacy)
    candidate = benchmark("candidate", created_at="2026-01-02")

    result = benchmark_compatibility(baseline, candidate)

    assert compatibility_field(
        result, "llm.output_schema_sha256.answer_evaluation"
    )["status"] == "unknown"
