"""Regression tests for a safe benchmark diagnostic ZIP."""
from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest

from app.services.benchmark_export import build_benchmark_export
from app.services.benchmark_runner import PHASE_RETRIEVAL_BASE
from app.services.eval_store import EvalNotFound
from app.tests.test_benchmark_runner import ADMIN, build, run_benchmark
from shared.auth import AuthIdentity
from shared.context import bound_context


def _archive(store, benchmark_id):
    with bound_context(**ADMIN.to_dict()):
        exported = build_benchmark_export(store, benchmark_id)
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(exported["content_base64"])))


def test_export_has_the_evidence_layout_and_strict_json():
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    with bound_context(**ADMIN.to_dict()):
        store.get_benchmark_run(benchmark["benchmark_id"])
        for row in store._memory[store.config.eval_benchmark_runs_collection]:
            if row["benchmark_id"] == benchmark["benchmark_id"]:
                row["operational_metrics"] = {"before": float("nan"), "after": None}

    with _archive(store, benchmark["benchmark_id"]) as archive:
        names = set(archive.namelist())
        assert {"README.md", "manifest.json", "dataset.json", "validation.json",
                "comparison.json",
                "summary.json", "metrics.json", "runtime.json", "errors.json",
                "benchmark.json"} <= names
        assert any(name.endswith("/per-item.json") for name in names)
        for name in names:
            if name.endswith(".json"):
                json.loads(
                    archive.read(name),
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
                )


def test_new_export_uses_its_snapshot_after_the_live_dataset_changes():
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    with bound_context(**ADMIN.to_dict()):
        store.update_dataset(
            dataset_id,
            items=[{"query": "changed", "relevant_chunk_ids": ["different"]}],
        )

    with _archive(store, benchmark["benchmark_id"]) as archive:
        evidence = json.loads(archive.read("dataset.json"))
    assert evidence["provenance"] == "immutable_benchmark_snapshot"
    assert evidence["dataset_version"] == benchmark["dataset_version"]
    assert evidence["dataset_sha256"] == benchmark["dataset_sha256"]
    assert evidence["items"][0]["query"] == "first"
    # Item identity is evidence — it is what the per-item files join on.
    # Authoring annotation is not, and stays out.
    assert all(item.get("item_id") for item in evidence["items"])
    assert all("notes" not in item for item in evidence["items"])


def test_new_export_survives_live_dataset_deletion():
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    with bound_context(**ADMIN.to_dict()):
        store.delete_dataset(dataset_id)

    with _archive(store, benchmark["benchmark_id"]) as archive:
        evidence = json.loads(archive.read("dataset.json"))
    assert evidence["provenance"] == "immutable_benchmark_snapshot"
    assert evidence["dataset_id"] == dataset_id


def test_legacy_export_marks_current_dataset_dependency_or_missing_dataset():
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    with bound_context(**ADMIN.to_dict()):
        for row in store._memory[store.config.eval_benchmark_runs_collection]:
            if row["benchmark_id"] == benchmark["benchmark_id"]:
                row.pop("dataset_snapshot")
        store.update_dataset(
            dataset_id, items=[{"query": "changed", "relevant_chunk_ids": ["c2"]}]
        )

    with _archive(store, benchmark["benchmark_id"]) as archive:
        evidence = json.loads(archive.read("dataset.json"))
    assert evidence["provenance"] == "legacy_current_dataset_dependent"
    assert evidence["items"][0]["query"] == "changed"

    with bound_context(**ADMIN.to_dict()):
        store.delete_dataset(dataset_id)
    with _archive(store, benchmark["benchmark_id"]) as archive:
        evidence = json.loads(archive.read("dataset.json"))
    assert evidence["provenance"] == "legacy_snapshot_missing_dataset_deleted"
    assert evidence["items"] is None


def test_export_excludes_answers_and_redacts_secrets():
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    with bound_context(**ADMIN.to_dict()):
        document = store.get_benchmark_run(benchmark["benchmark_id"])
        run_id = document["phases"][0]["run_id"]
        for row in store._memory[store.config.eval_runs_collection]:
            if row["run_id"] == run_id:
                row["per_item"][0]["answer"] = "private answer"
                row["config_snapshot"]["api_key"] = "do-not-export"

    with _archive(store, benchmark["benchmark_id"]) as archive:
        text = b"".join(archive.read(name) for name in archive.namelist()).decode("utf-8")
    assert "private answer" not in text
    assert "do-not-export" not in text
    assert "[redacted]" in text


def test_export_refuses_a_benchmark_owned_by_another_tenant():
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    other = AuthIdentity(tenant_id="tenant-b", user_id="admin-b", role="admin", admin_id="admin-b")

    with bound_context(**other.to_dict()), pytest.raises(EvalNotFound):
        build_benchmark_export(store, benchmark["benchmark_id"])
