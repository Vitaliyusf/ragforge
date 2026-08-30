from __future__ import annotations

import pytest

from app.eval.dataset import generate_scenarios
from app.eval.runner import EMBEDDING_DISCLAIMER, MEASUREMENT_CLASS, run_deterministic_benchmark


@pytest.fixture(scope="module")
def full_result():
    return run_deterministic_benchmark(generate_scenarios())


def test_runner_preserves_five_stage_boundaries_and_provenance(full_result):
    assert set(full_result["metrics"]) == {"stage_a", "stage_b", "stage_c", "stage_d", "stage_e"}
    assert full_result["summary"]["measurement_classification"] == MEASUREMENT_CLASS
    assert full_result["provenance"]["embedding"]["disclaimer"] == EMBEDDING_DISCLAIMER
    assert full_result["provenance"]["live_production_runtime"] == "DEFERRED / NOT MEASURED"
    assert full_result["provenance"]["token_usage"] is None


def test_full_runner_reports_no_cross_boundary_leakage(full_result):
    retrieval = full_result["metrics"]["stage_c"]

    assert retrieval["tenant_leakage"] == 0
    assert retrieval["user_leakage"] == 0
    # The known resurrection gap is also visible as a forbidden retrieval;
    # isolation leakage remains independently zero above.
    assert retrieval["forbidden_memory_retrieval_count"] == 24


def test_agent_boundary_counts_invalid_ids_and_safe_fallbacks(full_result):
    trajectory = full_result["metrics"]["stage_d"]

    assert trajectory["invalid_target_id_count"] == 24
    assert trajectory["forbidden_action_count"] == 0
    assert trajectory["no_mutation_fallback_correctness"] == pytest.approx(1.0)


def test_runner_attributes_known_resurrection_gap_without_mutating_production(full_result):
    lifecycle = full_result["metrics"]["stage_b"]

    assert lifecycle["resurrection_after_delete_count"] == 24
    failed = [
        row for row in full_result["per_scenario"]
        if "resurrection_attempt" in row["tags"]
    ]
    assert len(failed) == 24
    assert all(any(item["category"] == "lifecycle" for item in row["failures"]) for row in failed)


def test_evaluator_and_memory_failures_are_separate(full_result):
    assert full_result["errors"] == []
    assert "evaluator" not in full_result["summary"]["failure_attribution"]
