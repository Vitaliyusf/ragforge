"""Compatibility-aware comparison of one benchmark against an earlier run."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from app.services.benchmark_summary import summarize_benchmark

if TYPE_CHECKING:
    from app.services.eval_store import EvalStore

COMPARISON_VERSION = 1
TERMINAL_STATUSES = frozenset({"completed", "partial", "failed", "interrupted"})


def _path(document: Mapping[str, Any], path: str) -> Any:
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _compatibility_checks(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> Sequence[Tuple[str, str, Any, Any]]:
    checks = [
        (
            "dataset",
            "dataset_id",
            baseline.get("dataset_id"),
            candidate.get("dataset_id"),
        ),
        (
            "dataset",
            "dataset_version",
            baseline.get("dataset_version"),
            candidate.get("dataset_version"),
        ),
        (
            "dataset",
            "dataset_sha256",
            baseline.get("dataset_sha256"),
            candidate.get("dataset_sha256"),
        ),
    ]
    baseline_manifest = baseline.get("manifest")
    candidate_manifest = candidate.get("manifest")
    left = baseline_manifest if isinstance(baseline_manifest, Mapping) else {}
    right = candidate_manifest if isinstance(candidate_manifest, Mapping) else {}
    groups = {
        "config": ("dataset.phases", "chunking", "vector_store"),
        "model": ("embedding", "llm"),
        "retrieval": ("retrieval",),
    }
    for category, paths in groups.items():
        for path in paths:
            checks.append((category, path, _path(left, path), _path(right, path)))
    return checks


def benchmark_compatibility(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any]
) -> Dict[str, Any]:
    """Return explicit mismatch/unknown warnings; unknown cannot prove compatibility."""
    warnings = []
    for category, path, left, right in _compatibility_checks(baseline, candidate):
        if left is None or right is None:
            warnings.append({
                "category": category,
                "field": path,
                "kind": "unknown",
                "baseline": left,
                "candidate": right,
            })
        elif left != right:
            warnings.append({
                "category": category,
                "field": path,
                "kind": "mismatch",
                "baseline": left,
                "candidate": right,
            })
    return {"compatible": not warnings, "warnings": warnings}


def find_compatible_baseline(
    candidate: Mapping[str, Any], previous: Iterable[Mapping[str, Any]]
) -> Optional[Mapping[str, Any]]:
    """Choose the newest terminal, strictly earlier run whose provenance matches."""
    candidate_id = candidate.get("benchmark_id")
    candidate_time = str(candidate.get("created_at") or "")
    for run in previous:
        if run.get("benchmark_id") == candidate_id:
            continue
        if run.get("status") not in TERMINAL_STATUSES:
            continue
        created_at = str(run.get("created_at") or "")
        if candidate_time and created_at and created_at >= candidate_time:
            continue
        if benchmark_compatibility(run, candidate)["compatible"]:
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
    """Compare aligned measured metrics, keeping missing and zero denominators safe."""
    compatibility = benchmark_compatibility(baseline, candidate)
    left = _metrics(summarize_benchmark(baseline, runs=baseline_runs))
    right = _metrics(summarize_benchmark(candidate, runs=candidate_runs))
    metrics = []
    for name in sorted(set(left) | set(right)):
        baseline_value = left.get(name)
        candidate_value = right.get(name)
        delta = None
        percentage_delta = None
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
        })
    return {
        "comparison_version": COMPARISON_VERSION,
        "baseline_id": baseline.get("benchmark_id"),
        "candidate_id": candidate.get("benchmark_id"),
        **compatibility,
        "metrics": metrics,
    }


def comparison_for_candidate(
    store: "EvalStore", candidate: Mapping[str, Any]
) -> Dict[str, Any]:
    """Build an export-ready comparison using only tenant-scoped store methods."""
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
        warnings = (
            benchmark_compatibility(earlier[0], candidate)["warnings"]
            if earlier
            else [{
                "category": "baseline",
                "field": "benchmark_id",
                "kind": "missing",
                "baseline": None,
                "candidate": candidate.get("benchmark_id"),
            }]
        )
        return {
            "comparison_version": COMPARISON_VERSION,
            "baseline_id": None,
            "candidate_id": candidate.get("benchmark_id"),
            "compatible": False,
            "warnings": warnings,
            "metrics": [],
        }
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
