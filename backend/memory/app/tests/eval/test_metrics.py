from __future__ import annotations

import pytest

from app.eval.metrics import candidate_metrics, lifecycle_metrics, retrieval_metrics
from app.eval.trajectory import aggregate_trajectories, trajectory_row


def test_candidate_metrics_show_denominators_and_false_durable_candidates():
    measured = candidate_metrics(
        [
            {"expected_candidate_ids": ["a"], "actual_candidate_ids": ["a"]},
            {"expected_candidate_ids": [], "actual_candidate_ids": ["bad"]},
            {"expected_candidate_ids": [], "actual_candidate_ids": []},
        ]
    )

    assert measured["candidate_precision"] == pytest.approx(0.5)
    assert measured["candidate_recall"] == pytest.approx(1.0)
    assert measured["irrelevant_no_op_correctness"] == pytest.approx(0.5)
    assert measured["false_durable_candidate_count"] == 1
    assert measured["denominators"] == {
        "expected_candidates": 1,
        "proposed_candidates": 2,
        "no_op_scenarios": 2,
    }


def test_retrieval_metrics_keep_security_staleness_and_ranking_separate():
    measured = retrieval_metrics(
        [
            {
                "expected_ids": ["current"],
                "actual_ids": ["current", "noise"],
                "forbidden_ids": [],
                "stale_ids": ["old"],
                "graded_relevance": {"current": 2},
            },
            {
                "expected_ids": ["old"],
                "actual_ids": ["old"],
                "forbidden_ids": [],
                "stale_ids": [],
                "as_of": "2025-01-01T00:00:00+00:00",
                "graded_relevance": {"old": 1},
                "tenant_leakage": 1,
            },
        ]
    )

    assert measured["hit_at_1"] == pytest.approx(1.0)
    assert measured["recall_at_5"] == pytest.approx(1.0)
    assert measured["mrr"] == pytest.approx(1.0)
    assert measured["ndcg"] == pytest.approx(1.0)
    assert measured["irrelevant_memory_rate"] == pytest.approx(1 / 3)
    assert measured["stale_memory_rate"] == pytest.approx(0.0)
    assert measured["tenant_leakage"] == 1
    assert measured["user_leakage"] == 0


def test_lifecycle_metrics_do_not_hide_resurrection_or_destructive_failures():
    measured = lifecycle_metrics(
        [
            {
                "expected_action": "create",
                "actual_action": "create",
                "active_state_correct": True,
            },
            {
                "expected_action": "resurrection_prevented",
                "actual_action": "create",
                "active_state_correct": False,
                "false_destructive_mutation": 1,
            },
        ]
    )

    assert measured["create"]["precision"] == pytest.approx(0.5)
    assert measured["create"]["recall"] == pytest.approx(1.0)
    assert measured["resurrection_after_delete_count"] == 1
    assert measured["false_destructive_mutation_count"] == 1


def test_trajectory_rejects_destructive_substitution_for_an_update():
    row = trajectory_row(
        ["search_memory", "compare_existing", "update_memory"],
        ["search_memory", "delete_memory", "create_memory"],
        forbidden=["delete_memory"],
    )
    aggregate = aggregate_trajectories([row])

    assert row["strict_match"] is False
    assert row["allowed_sequence"] is False
    assert aggregate["forbidden_action_count"] == 1
    assert aggregate["unsafe_destructive_trajectory_count"] == 1
