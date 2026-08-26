"""Compatibility-aware comparison of one benchmark against an earlier run."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, Mapping, Optional, Sequence

from app.services.benchmark_summary import summarize_benchmark

if TYPE_CHECKING:
    from app.services.eval_store import EvalStore

COMPARISON_VERSION = 2
TERMINAL_STATUSES = frozenset({"completed", "partial", "failed", "interrupted"})

CRITICAL_COMPATIBILITY_FIELDS: Sequence[tuple[str, str, str]] = (
    ("dataset", "dataset_id", "dataset_id"),
    ("dataset", "dataset_version", "dataset_version"),
    ("dataset", "dataset_sha256", "dataset_sha256"),
    ("config", "dataset.phases", "manifest.dataset.phases"),
    ("build", "build.git_sha", "manifest.build.git_sha"),
    ("build", "build.git_branch", "manifest.build.git_branch"),
    ("build", "build.build_timestamp", "manifest.build.build_timestamp"),
    ("build", "build.image_tag", "manifest.build.image_tag"),
    ("model", "embedding.model", "manifest.embedding.model"),
    ("model", "embedding.vector_size", "manifest.embedding.vector_size"),
    ("config", "chunking.size", "manifest.chunking.size"),
    ("config", "chunking.overlap", "manifest.chunking.overlap"),
    ("config", "chunking.strategy", "manifest.chunking.strategy"),
    ("config", "vector_store.type", "manifest.vector_store.type"),
    ("config", "vector_store.collection", "manifest.vector_store.collection"),
    ("model", "llm.implementation", "manifest.llm.implementation"),
    ("model", "llm.chat_model", "manifest.llm.chat_model"),
    ("model", "llm.max_model_len", "manifest.llm.max_model_len"),
    ("model", "llm.quantization", "manifest.llm.quantization"),
    (
        "retrieval",
        "retrieval.retrieval_strategy",
        "manifest.retrieval.retrieval_strategy",
    ),
    ("retrieval", "retrieval.context_k", "manifest.retrieval.context_k"),
    ("retrieval", "retrieval.eval_candidate_k", "manifest.retrieval.eval_candidate_k"),
    ("retrieval", "retrieval.pass_two_active", "manifest.retrieval.pass_two_active"),
    ("retrieval", "retrieval.reranker_active", "manifest.retrieval.reranker_active"),
    (
        "retrieval",
        "retrieval.hybrid_search_active",
        "manifest.retrieval.hybrid_search_active",
    ),
)


def _path(document: Mapping[str, Any], path: str) -> Any:
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _is_unobserved(document: Mapping[str, Any], source_path: str) -> bool:
    if not source_path.startswith("manifest."):
        return False
    manifest = document.get("manifest")
    if not isinstance(manifest, Mapping):
        return True
    unobserved = manifest.get("unobserved")
    return isinstance(unobserved, list) and source_path[9:] in unobserved


def _conditional_fields(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> list[tuple[str, str, str]]:
    fields: list[tuple[str, str, str]] = []
    for active_field, details in (
        (
            "manifest.retrieval.pass_two_active",
            ("pass_two_chunk_threshold", "pass_two_score_threshold"),
        ),
        (
            "manifest.retrieval.reranker_active",
            ("reranker_implementation", "reranker_model"),
        ),
        (
            "manifest.retrieval.hybrid_search_active",
            ("hybrid_search_strategy", "hybrid_search_alpha_applied"),
        ),
    ):
        if _path(baseline, active_field) is True or _path(candidate, active_field) is True:
            for detail in details:
                fields.append(
                    (
                        "retrieval",
                        f"retrieval.{detail}",
                        f"manifest.retrieval.{detail}",
                    )
                )
    return fields


def _compatibility_checks(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> list[Dict[str, Any]]:
    checks = []
    fields = [*CRITICAL_COMPATIBILITY_FIELDS, *_conditional_fields(baseline, candidate)]
    for category, field, source_path in fields:
        left = _path(baseline, source_path)
        right = _path(candidate, source_path)
        if (
            left is None
            or right is None
            or _is_unobserved(baseline, source_path)
            or _is_unobserved(candidate, source_path)
        ):
            status = "unknown"
            reason = "critical provenance is missing or unobserved on at least one run"
        elif left != right:
            status = "different"
            reason = "known critical provenance values differ"
        else:
            status = "same"
            reason = "known critical provenance values are equal"
        checks.append({
            "category": category,
            "field": field,
            "baseline": left,
            "candidate": right,
            "status": status,
            "reason": reason,
        })
    return checks


def benchmark_compatibility(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> Dict[str, Any]:
    """Classify critical provenance without treating unknown as equality."""
    fields = _compatibility_checks(baseline, candidate)
    statuses = {check["status"] for check in fields}
    if "different" in statuses:
        state = "incompatible"
        conclusion = "known incompatible comparison"
    elif "unknown" in statuses:
        state = "unknown"
        conclusion = "compatibility cannot be proven"
    else:
        state = "compatible"
        conclusion = "safe apples-to-apples comparison"
    warnings = [
        {
            "category": check["category"],
            "field": check["field"],
            "kind": "mismatch" if check["status"] == "different" else "unknown",
            "baseline": check["baseline"],
            "candidate": check["candidate"],
            "reason": check["reason"],
        }
        for check in fields
        if check["status"] != "same"
    ]
    return {
        "compatible": state == "compatible",
        "compatibility_status": state,
        "compatibility_conclusion": conclusion,
        "compatibility_fields": fields,
        "warnings": warnings,
    }


def find_compatible_baseline(
    candidate: Mapping[str, Any], previous: Iterable[Mapping[str, Any]]
) -> Optional[Mapping[str, Any]]:
    """Choose the newest terminal, strictly earlier proven-compatible run."""
    candidate_id = candidate.get("benchmark_id")
    candidate_time = str(candidate.get("created_at") or "")
    for run in previous:
        if (
            run.get("benchmark_id") == candidate_id
            or run.get("status") not in TERMINAL_STATUSES
        ):
            continue
        created_at = str(run.get("created_at") or "")
        if candidate_time and created_at and created_at >= candidate_time:
            continue
        if (
            benchmark_compatibility(run, candidate)["compatibility_status"]
            == "compatible"
        ):
            return run
    return None


def _metrics(summary: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    values: Dict[str, Optional[float]] = {}
    phases = summary.get("phases")
    for phase in phases if isinstance(phases, list) else ():
        if not isinstance(phase, Mapping) or not phase.get("name"):
            continue
        prefix = f"phases.{phase['name']}"
        retrieval = phase.get("retrieval")
        if isinstance(retrieval, Mapping):
            values[f"{prefix}.retrieval.mrr"] = retrieval.get("mrr")
            for metric in (
                "recall_at_k",
                "precision_at_k",
                "hit_rate_at_k",
                "ndcg_at_k",
            ):
                at_k = retrieval.get(metric)
                if isinstance(at_k, Mapping):
                    for k, value in at_k.items():
                        values[f"{prefix}.retrieval.{metric}.{k}"] = value
        latency = phase.get("latency_ms")
        if isinstance(latency, Mapping):
            for metric in ("mean", "p50", "p95", "p99"):
                values[f"{prefix}.latency_ms.{metric}"] = latency.get(metric)
        quality = phase.get("answer_quality")
        if isinstance(quality, Mapping):
            for metric in (
                "groundedness",
                "citation_precision",
                "citation_recall",
                "unsupported_claims",
            ):
                block = quality.get(metric)
                if isinstance(block, Mapping):
                    values[f"{prefix}.answer_quality.{metric}"] = block.get("mean")
            for metric in ("hallucination_rate", "hallucination_severe_rate"):
                values[f"{prefix}.answer_quality.{metric}"] = quality.get(metric)
    return values


def compare_benchmarks(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    baseline_runs: Optional[Iterable[Mapping[str, Any]]] = None,
    candidate_runs: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compare metrics while marking deltas non-authoritative when needed."""
    compatibility = benchmark_compatibility(baseline, candidate)
    authoritative = compatibility["compatibility_status"] == "compatible"
    left = _metrics(summarize_benchmark(baseline, runs=baseline_runs))
    right = _metrics(summarize_benchmark(candidate, runs=candidate_runs))
    metrics = []
    for name in sorted(set(left) | set(right)):
        baseline_value = left.get(name)
        candidate_value = right.get(name)
        delta = percentage_delta = None
        if isinstance(baseline_value, (int, float)) and isinstance(
            candidate_value, (int, float)
        ):
            delta = candidate_value - baseline_value
            if baseline_value != 0:
                percentage_delta = (delta / abs(baseline_value)) * 100.0
        metrics.append({
            "metric": name,
            "baseline": baseline_value,
            "candidate": candidate_value,
            "absolute_delta": delta,
            "percentage_delta": percentage_delta,
            "authoritative": authoritative,
        })
    return {
        "comparison_version": COMPARISON_VERSION,
        "baseline_id": baseline.get("benchmark_id"),
        "candidate_id": candidate.get("benchmark_id"),
        **compatibility,
        "metrics_authoritative": authoritative,
        "metrics": metrics,
    }


def comparison_for_candidate(
    store: "EvalStore", candidate: Mapping[str, Any]
) -> Dict[str, Any]:
    """Build an export-ready comparison using only tenant-scoped methods."""
    history = store.list_benchmark_runs(candidate.get("dataset_id"), limit=100)
    baseline = find_compatible_baseline(candidate, history)
    if baseline is None:
        earlier = [
            run
            for run in history
            if run.get("benchmark_id") != candidate.get("benchmark_id")
            and run.get("status") in TERMINAL_STATUSES
            and (
                not candidate.get("created_at")
                or not run.get("created_at")
                or str(run["created_at"]) < str(candidate["created_at"])
            )
        ]
        if not earlier:
            return {
                "comparison_version": COMPARISON_VERSION,
                "baseline_id": None,
                "candidate_id": candidate.get("benchmark_id"),
                "compatible": False,
                "compatibility_status": "unknown",
                "compatibility_conclusion": "compatibility cannot be proven",
                "compatibility_fields": [],
                "warnings": [
                    {
                        "category": "baseline",
                        "field": "benchmark_id",
                        "kind": "missing",
                        "baseline": None,
                        "candidate": candidate.get("benchmark_id"),
                        "reason": "no earlier terminal benchmark is available",
                    }
                ],
                "metrics_authoritative": False,
                "metrics": [],
            }
        baseline = earlier[0]
    return compare_benchmarks(
        baseline,
        candidate,
        baseline_runs=_phase_runs(store, baseline),
        candidate_runs=_phase_runs(store, candidate),
    )


def _phase_runs(store: "EvalStore", benchmark: Mapping[str, Any]) -> list[Dict[str, Any]]:
    run_ids = []
    for phase in benchmark.get("phases") or []:
        run_id = phase.get("run_id") if isinstance(phase, Mapping) else None
        if run_id:
            run_ids.append(str(run_id))
    return store.get_runs(run_ids)
