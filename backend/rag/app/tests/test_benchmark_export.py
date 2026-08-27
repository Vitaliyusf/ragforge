"""Regression tests for a safe benchmark diagnostic ZIP."""
from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest

from app.services.benchmark_export import (
    MAX_TEXT_BYTES,
    _json_bytes,
    _sanitize,
    _trace_evidence,
    build_benchmark_export,
)
from app.services.benchmark_runner import PHASE_RETRIEVAL_BASE
from app.services.eval_store import EvalNotFound
from app.tests.test_benchmark_runner import ADMIN, build, run_benchmark
from shared.auth import AuthIdentity
from shared.context import bound_context


def _archive(store, benchmark_id):
    with bound_context(**ADMIN.to_dict()):
        exported = build_benchmark_export(store, benchmark_id)
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(exported["content_base64"])))


def test_export_has_the_evidence_layout_and_strict_json(monkeypatch):
    expected_budgets = {
        "answer_generation": 128,
        "answer_evaluation": 512,
        "content_risk_scan": 128,
        "query_rewrite": 128,
        "memory_extraction": 512,
    }
    for action, budget in expected_budgets.items():
        monkeypatch.setenv(f"{action.upper()}_MAX_TOKENS", str(budget))
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
                "benchmark.json", "truncation.json"} <= names
        assert any(name.endswith("/per-item.json") for name in names)
        exported_phase = json.loads(archive.read("benchmark.json"))["phases"][0]
        manifest = json.loads(archive.read("manifest.json"))
        runtime = json.loads(archive.read("runtime.json"))
        assert runtime["llm"] == manifest["llm"]
        assert set(runtime["llm"]["max_tokens"]) == {
            "answer_generation",
            "answer_evaluation",
            "content_risk_scan",
            "query_rewrite",
            "memory_extraction",
        }
        assert runtime["llm"]["max_tokens"] == expected_budgets
        assert exported_phase["phase_started_at"]
        assert exported_phase["phase_finished_at"]
        assert exported_phase["phase_wall_clock_ms"] >= 0
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


def test_per_item_export_identifies_guardrail_outcome_and_stage():
    evidence = _trace_evidence(
        [
            {
                "item_id": "blocked-1",
                "outcome": "guardrail_blocked",
                "guardrail_stage": "input",
                "timed_out": False,
                "error_class": None,
                "query": "private prompt",
            }
        ]
    )

    assert evidence == [
        {
            "item_id": "blocked-1",
            "outcome": "guardrail_blocked",
            "guardrail_stage": "input",
            "timed_out": False,
            "error_class": None,
        }
    ]


def test_legacy_per_item_export_uses_null_for_unknown_outcome_fields():
    evidence = _trace_evidence([{"item_id": "legacy-1", "skipped": True}])

    assert evidence[0]["outcome"] is None
    assert evidence[0]["guardrail_stage"] is None
    assert evidence[0]["timed_out"] is None
    assert evidence[0]["error_class"] is None


def test_per_item_export_includes_explicit_timing_and_reads_legacy_rows():
    timed = _trace_evidence(
        [
            {
                "item_id": "timed-1",
                "latency_ms": 12.0,
                "queue_wait_ms": 2.0,
                "execution_ms": 10.0,
                "total_elapsed_ms": 12.0,
            },
            {"item_id": "legacy-1", "latency_ms": 7.0},
        ]
    )

    assert timed[0]["queue_wait_ms"] == 2.0
    assert timed[0]["execution_ms"] == 10.0
    assert timed[0]["total_elapsed_ms"] == 12.0
    assert timed[1]["latency_ms"] == 7.0
    assert "queue_wait_ms" not in timed[1]


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        "NaN",
        "+Inf",
        "-Inf",
        "Infinity",
        "+Infinity",
        "-Infinity",
    ],
)
def test_non_finite_numeric_and_string_evidence_becomes_null(value):
    truncation = {"text_fields_truncated": 0, "examples": []}
    sanitized = _sanitize(
        {"sample": [value]}, path="metrics.json", truncation=truncation
    )

    assert sanitized == {"sample": [None]}
    assert json.loads(_json_bytes(sanitized)) == {"sample": [None]}


def test_token_metric_allowlist_preserves_prometheus_results_and_redacts_credentials():
    truncation = {"text_fields_truncated": 0, "examples": []}
    prometheus_result = [
        {
            "metric": {"request_type": "answer_generation", "traffic_class": "eval"},
            "value": [1730000000, "42.5"],
        }
    ]
    document = {
        "access_token": "access-secret",
        "refresh_token": "refresh-secret",
        "authorization": "Bearer secret",
        "api_key": "api-secret",
        "session_token": "session-secret",
        "private_token": "private-secret",
        "llm_input_token_rate": prometheus_result,
        "llm_output_token_rate": prometheus_result,
        "llm_total_token_rate": prometheus_result,
        "llm_finish_reason_rate": prometheus_result,
        "llm_output_tokens_p50_by_request_type": prometheus_result,
        "llm_output_tokens_p95_by_request_type": prometheus_result,
        "llm_output_tokens_p99_by_request_type": prometheus_result,
    }

    sanitized = _sanitize(document, path="metrics.json", truncation=truncation)

    for key in (
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "session_token",
        "private_token",
    ):
        assert sanitized[key] == "[redacted]"
    for key in document.keys() - {
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "session_token",
        "private_token",
    }:
        assert sanitized[key] == prometheus_result
    json.loads(_json_bytes(sanitized))


def test_token_metric_allowlist_does_not_allow_arbitrary_string_values():
    truncation = {"text_fields_truncated": 0, "examples": []}

    sanitized = _sanitize(
        {"llm_output_token_rate": "not-prometheus-evidence"},
        path="metrics.json",
        truncation=truncation,
    )

    assert sanitized["llm_output_token_rate"] == "[redacted]"


@pytest.mark.parametrize(
    "root_path",
    ["manifest.json", "runtime.json"],
)
def test_safe_token_budget_provenance_survives_only_at_approved_export_paths(
    root_path,
):
    truncation = {"text_fields_truncated": 0, "examples": []}
    budgets = {
        "answer_generation": 128,
        "answer_evaluation": 512,
        "content_risk_scan": 128,
        "query_rewrite": 128,
        "memory_extraction": 512,
    }
    document = {
        "llm": {"max_tokens": budgets},
        "access_token": "access-secret",
        "refresh_token": "refresh-secret",
        "some_token": "secret-value",
    }

    sanitized = _sanitize(document, path=root_path, truncation=truncation)

    assert sanitized["llm"]["max_tokens"] == budgets
    assert all(
        isinstance(value, int)
        for value in sanitized["llm"]["max_tokens"].values()
    )
    assert sanitized["access_token"] == "[redacted]"
    assert sanitized["refresh_token"] == "[redacted]"
    assert sanitized["some_token"] == "[redacted]"


def test_token_budget_exception_rejects_unapproved_paths_and_malformed_maps():
    truncation = {"text_fields_truncated": 0, "examples": []}
    budgets = {
        "answer_generation": 128,
        "answer_evaluation": 512,
        "content_risk_scan": 128,
        "query_rewrite": 128,
        "memory_extraction": 512,
    }

    unrelated = _sanitize(
        {"llm": {"max_tokens": budgets}},
        path="comparison.json",
        truncation=truncation,
    )
    unknown = _sanitize(
        {"llm": {"max_tokens": {**budgets, "unknown": 1}}},
        path="manifest.json",
        truncation=truncation,
    )
    text = _sanitize(
        {"llm": {"max_tokens": {**budgets, "answer_generation": "secret"}}},
        path="runtime.json",
        truncation=truncation,
    )
    boolean = _sanitize(
        {"llm": {"max_tokens": {**budgets, "answer_generation": True}}},
        path="runtime.json",
        truncation=truncation,
    )

    assert unrelated["llm"]["max_tokens"] == "[redacted]"
    assert unknown["llm"]["max_tokens"] == "[redacted]"
    assert text["llm"]["max_tokens"] == "[redacted]"
    assert boolean["llm"]["max_tokens"] == "[redacted]"


def test_safe_token_budget_map_normalizes_non_finite_values_to_null():
    truncation = {"text_fields_truncated": 0, "examples": []}
    budgets = {
        "answer_generation": float("nan"),
        "answer_evaluation": float("inf"),
        "content_risk_scan": 128,
        "query_rewrite": 128,
        "memory_extraction": 512,
    }

    sanitized = _sanitize(
        {"llm": {"max_tokens": budgets}},
        path="manifest.json",
        truncation=truncation,
    )

    assert sanitized["llm"]["max_tokens"]["answer_generation"] is None
    assert sanitized["llm"]["max_tokens"]["answer_evaluation"] is None
    json.loads(_json_bytes(sanitized))


def test_export_reports_text_truncation_explicitly():
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    oversized = "x" * (MAX_TEXT_BYTES + 100)
    with bound_context(**ADMIN.to_dict()):
        document = store.get_benchmark_run(benchmark["benchmark_id"])
        run_id = document["phases"][0]["run_id"]
        for row in store._memory[store.config.eval_runs_collection]:
            if row["run_id"] == run_id:
                row["error"] = oversized

    with _archive(store, benchmark["benchmark_id"]) as archive:
        report = json.loads(archive.read("truncation.json"))
        summary_name = next(
            name for name in archive.namelist() if name.endswith("/summary.json")
        )
        summary = json.loads(archive.read(summary_name))

    assert report["text_fields_truncated"] >= 1
    assert any(example["path"].endswith(".error") for example in report["examples"])
    assert len(summary["error"].encode("utf-8")) == MAX_TEXT_BYTES


def test_prepare_run_export_integration_uses_bulk_tenant_scoped_run_loading():
    """One tenant can prepare labels, finish a benchmark, and export it."""
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    original_get_run = store.get_run

    def refuse_n_plus_one(_run_id):
        raise AssertionError("export must bulk-load phase runs")

    store.get_run = refuse_n_plus_one
    try:
        with _archive(store, benchmark["benchmark_id"]) as archive:
            dataset = json.loads(archive.read("dataset.json"))
            summary = json.loads(archive.read("summary.json"))
    finally:
        store.get_run = original_get_run

    assert dataset["dataset_id"] == dataset_id
    assert dataset["provenance"] == "immutable_benchmark_snapshot"
    assert summary["benchmark_id"] == benchmark["benchmark_id"]


def test_export_refuses_a_benchmark_owned_by_another_tenant():
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    other = AuthIdentity(tenant_id="tenant-b", user_id="admin-b", role="admin", admin_id="admin-b")

    with bound_context(**other.to_dict()), pytest.raises(EvalNotFound):
        build_benchmark_export(store, benchmark["benchmark_id"])
