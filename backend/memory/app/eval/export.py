"""Strict JSON and reproducible ZIP exports for one memory benchmark result."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any, Dict, Mapping

from app.eval.dataset import MemoryScenario, canonical_dataset_bytes


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8")


def build_export(result: Mapping[str, Any], scenarios: list[MemoryScenario]) -> bytes:
    """Return a bounded, machine-readable archive with stable member metadata."""
    documents: Dict[str, bytes] = {
        "manifest.json": _json_bytes(result["manifest"]),
        "dataset.json": canonical_dataset_bytes(scenarios),
        "summary.json": _json_bytes(result["summary"]),
        "metrics.json": _json_bytes(result["metrics"]),
        "per-scenario.json": _json_bytes(result["per_scenario"]),
        "errors.json": _json_bytes(result["errors"]),
        "provenance.json": _json_bytes(result["provenance"]),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(documents):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, documents[name])
    return output.getvalue()


def export_manifest(payload: bytes) -> Dict[str, Any]:
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
