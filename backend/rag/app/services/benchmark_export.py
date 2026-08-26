"""Safe, bounded diagnostic archives for one benchmark run.

The archive is assembled in memory.  It never uses a caller-controlled path
or leaves a temporary file behind, and every document is JSON encoded with
``allow_nan=False`` so an export remains consumable by strict tools.
"""
from __future__ import annotations

import base64
import io
import json
import math
import re
import zipfile
from typing import Any, Dict, Iterable, Mapping

from app.services.benchmark_summary import summarize_benchmark
from app.services.eval_store import EvalNotFound, EvalStore, EvalValidationError

MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 16 * 1024
_SECRET_KEY = re.compile(r"(?:secret|password|api[_-]?key|token|authorization)", re.I)


class BenchmarkExportTooLarge(EvalValidationError):
    """The requested evidence is larger than the safe archive limit."""


def build_benchmark_export(store: EvalStore, benchmark_id: str) -> Dict[str, str]:
    """Return a base64 ZIP containing one caller-authorised benchmark.

    Store lookups deliberately use their public methods: each method applies
    the admin and tenant predicates, including for every phase run.
    """
    benchmark = store.get_benchmark_run(benchmark_id)
    runs = _phase_runs(store, benchmark.get("phases"))
    summary = summarize_benchmark(benchmark, runs=runs)
    documents: Dict[str, Any] = {
        "manifest.json": benchmark.get("manifest"),
        "dataset.json": _dataset_evidence(store, benchmark),
        "validation.json": {run["run_id"]: run.get("label_validation") for run in runs},
        "summary.json": summary,
        "metrics.json": benchmark.get("operational_metrics"),
        "runtime.json": _runtime_evidence(benchmark.get("manifest")),
        "errors.json": _errors(benchmark, runs),
        "benchmark.json": _benchmark_evidence(benchmark),
    }
    for index, run in enumerate(runs, start=1):
        prefix = f"phases/{index:02d}-{_safe_name(str(run.get('run_id') or 'run'))}"
        documents[f"{prefix}/summary.json"] = _run_evidence(run)
        documents[f"{prefix}/per-item.json"] = _trace_evidence(run.get("per_item"))

    payload = _zip(documents)
    return {
        "filename": f"benchmark-{_safe_name(str(benchmark.get('benchmark_id') or 'export'))}.zip",
        "content_base64": base64.b64encode(payload).decode("ascii"),
    }


def _phase_runs(store: EvalStore, phases: Any) -> list[Dict[str, Any]]:
    runs = []
    for phase in phases if isinstance(phases, list) else []:
        run_id = phase.get("run_id") if isinstance(phase, Mapping) else None
        if run_id:
            runs.append(store.get_run(str(run_id)))
    return runs


def _dataset_evidence(store: EvalStore, benchmark: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = benchmark.get("dataset_snapshot")
    if isinstance(snapshot, Mapping):
        return {"provenance": "immutable_benchmark_snapshot", **dict(snapshot)}

    # Old documents have no immutable labels.  They remain exportable, but a
    # live Golden Set is explicitly evidence of *today's* labels only.
    try:
        dataset = store.get_dataset(str(benchmark.get("dataset_id") or ""))
    except EvalNotFound:
        return {
            "provenance": "legacy_snapshot_missing_dataset_deleted",
            "dataset_id": benchmark.get("dataset_id"),
            "benchmark_dataset_version": benchmark.get("dataset_version"),
            "benchmark_dataset_sha256": benchmark.get("dataset_sha256"),
            "items": None,
        }
    return {
        "provenance": "legacy_current_dataset_dependent",
        "dataset_id": dataset.get("dataset_id"),
        "dataset_version": dataset.get("dataset_version"),
        "dataset_sha256": dataset.get("dataset_sha256"),
        "items": dataset.get("items"),
        "benchmark_dataset_version": benchmark.get("dataset_version"),
        "benchmark_dataset_sha256": benchmark.get("dataset_sha256"),
    }


def _benchmark_evidence(benchmark: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: benchmark.get(key)
        for key in (
            "benchmark_id",
            "dataset_id",
            "dataset_version",
            "dataset_sha256",
            "created_at",
            "started_at",
            "finished_at",
            "status",
            "progress",
            "phases",
        )
    }


def _runtime_evidence(manifest: Any) -> Any:
    if not isinstance(manifest, Mapping):
        return None
    return {
        key: manifest.get(key)
        for key in ("captured_at", "build", "runtime", "retrieval")
    }


def _run_evidence(run: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: run.get(key)
        for key in (
            "run_id",
            "dataset_id",
            "dataset_version",
            "dataset_sha256",
            "started_at",
            "finished_at",
            "status",
            "match_mode",
            "mode",
            "pipeline_mode",
            "benchmark_id",
            "config_snapshot",
            "label_validation",
            "results",
            "error",
        )
    }


def _trace_evidence(rows: Any) -> list[Any]:
    # Keep bounded retrieval lineage, IDs and scoring evidence; answer and raw
    # document/context text are intentionally excluded from a diagnostic ZIP.
    allowed = (
        "item_id",
        "match_mode",
        "expected_ids",
        "retrieved_ids",
        "first_hit_rank",
        "reciprocal_rank",
        "recall_at_10",
        "latency_ms",
        "skipped",
        "unscorable",
        "error",
        "scores",
        "retrieval_trace",
        "groundedness",
        "citation_precision",
        "citation_recall",
        "unsupported_claim_count",
        "hallucination_verdict",
    )
    return [
        {key: row.get(key) for key in allowed if key in row}
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, Mapping)
    ]


def _errors(benchmark: Mapping[str, Any], runs: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    return {
        "benchmark_error": benchmark.get("error"),
        "runs": [
            {"run_id": run.get("run_id"), "error": run.get("error")}
            for run in runs
            if run.get("error")
        ],
    }


def _zip(documents: Mapping[str, Any]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", _README)
        for name, document in documents.items():
            archive.writestr(name, _json_bytes(_sanitize(document)))
    payload = output.getvalue()
    if len(payload) > MAX_EXPORT_BYTES:
        raise BenchmarkExportTooLarge("Benchmark export exceeds the maximum archive size")
    return payload


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sanitize(value: Any, key: str = "") -> Any:
    if _SECRET_KEY.search(key):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(name): _sanitize(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, key) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str):
        return value.encode("utf-8")[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)[:80] or "export"


_README = """# RAGForge benchmark diagnostic export

This archive contains a tenant-scoped benchmark's recorded evidence. New
benchmarks export their immutable canonical scoring snapshot. Legacy exports
state explicitly when their dataset evidence depends on today's Golden Set or
when that Golden Set has been deleted. `null` means unmeasured or unavailable,
never zero. Per-item files contain bounded scoring and retrieval lineage only;
raw document/context text and answer text are excluded.
"""
