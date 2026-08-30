"""Stage-specific deterministic metrics for labelled memory observations."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Sequence


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def candidate_metrics(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    true_positive = false_positive = false_negative = correct_no_op = no_op_total = 0
    for row in rows:
        expected = set(row.get("expected_candidate_ids") or [])
        actual = set(row.get("actual_candidate_ids") or [])
        true_positive += len(expected & actual)
        false_positive += len(actual - expected)
        false_negative += len(expected - actual)
        if not expected:
            no_op_total += 1
            correct_no_op += int(not actual)
    return {
        "candidate_precision": _ratio(true_positive, true_positive + false_positive),
        "candidate_recall": _ratio(true_positive, true_positive + false_negative),
        "irrelevant_no_op_correctness": _ratio(correct_no_op, no_op_total),
        "false_durable_candidate_count": false_positive,
        "denominators": {
            "expected_candidates": true_positive + false_negative,
            "proposed_candidates": true_positive + false_positive,
            "no_op_scenarios": no_op_total,
        },
    }


def lifecycle_metrics(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    materialized = list(rows)
    actions = (
        "create",
        "no_op",
        "update",
        "supersede",
        "duplicate_exact",
        "duplicate_semantic",
        "coexist",
        "delete",
        "resurrection_prevented",
        "idempotent",
        "historical",
        "needs_review",
    )
    metrics: Dict[str, Any] = {}
    for action in actions:
        expected = sum(row.get("expected_action") == action for row in materialized)
        actual = sum(row.get("actual_action") == action for row in materialized)
        correct = sum(
            row.get("expected_action") == action and row.get("actual_action") == action
            for row in materialized
        )
        metrics[action] = {
            "precision": _ratio(correct, actual),
            "recall": _ratio(correct, expected),
            "correct": correct,
            "expected": expected,
            "actual": actual,
        }
    duplicate_expected = sum(
        row.get("expected_action") in {"duplicate_exact", "duplicate_semantic"}
        for row in materialized
    )
    duplicate_correct = sum(
        row.get("expected_action") == row.get("actual_action")
        and row.get("expected_action") in {"duplicate_exact", "duplicate_semantic"}
        for row in materialized
    )
    metrics.update(
        {
            "duplicate_suppression_accuracy": _ratio(duplicate_correct, duplicate_expected),
            "active_state_correctness": _ratio(
                sum(bool(row.get("active_state_correct")) for row in materialized),
                len(materialized),
            ),
            "false_destructive_mutation_count": sum(
                int(row.get("false_destructive_mutation", 0)) for row in materialized
            ),
            "unresolved_needs_review_count": sum(
                row.get("actual_action") == "needs_review" for row in materialized
            ),
            "resurrection_after_delete_count": sum(
                row.get("expected_action") == "resurrection_prevented"
                and row.get("actual_action") != "resurrection_prevented"
                for row in materialized
            ),
            "scenario_count": len(materialized),
        }
    )
    return metrics


def _dcg(ids: Sequence[str], grades: Mapping[str, int]) -> float:
    return float(
        sum((2 ** grades.get(item, 0) - 1) / math.log2(rank + 2) for rank, item in enumerate(ids))
    )


def retrieval_metrics(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    materialized = list(rows)
    scorable = [row for row in materialized if row.get("expected_ids")]
    recalls: Dict[int, List[float]] = {1: [], 3: [], 5: []}
    hit_one: List[float] = []
    reciprocal_ranks: List[float] = []
    ndcgs: List[float] = []
    irrelevant = stale = returned = tenant_leakage = user_leakage = forbidden = 0
    current_checks: List[bool] = []
    historical_checks: List[bool] = []
    abstention_checks: List[bool] = []
    for row in materialized:
        actual = list(row.get("actual_ids") or [])
        expected = set(row.get("expected_ids") or [])
        forbidden_ids = set(row.get("forbidden_ids") or [])
        stale_ids = set(row.get("stale_ids") or [])
        returned += len(actual)
        irrelevant += sum(item not in expected for item in actual)
        stale += sum(item in stale_ids for item in actual)
        forbidden += sum(item in forbidden_ids for item in actual)
        tenant_leakage += int(row.get("tenant_leakage", 0))
        user_leakage += int(row.get("user_leakage", 0))
        if row.get("expected_abstention"):
            abstention_checks.append(not actual)
        if row.get("as_of"):
            historical_checks.append(bool(expected.intersection(actual[:1])))
        elif expected:
            current_checks.append(bool(expected.intersection(actual[:1])))
        if not expected:
            continue
        hit_one.append(float(bool(expected.intersection(actual[:1]))))
        for k in recalls:
            recalls[k].append(len(expected.intersection(actual[:k])) / len(expected))
        ranks = [rank for rank, item in enumerate(actual, start=1) if item in expected]
        reciprocal_ranks.append(1 / min(ranks) if ranks else 0.0)
        grades = dict(row.get("graded_relevance") or {item: 1 for item in expected})
        ideal = sorted(grades, key=lambda item: grades[item], reverse=True)
        denominator = _dcg(ideal, grades)
        ndcgs.append(_dcg(actual[: len(ideal)], grades) / denominator if denominator else 0.0)
    def average(values: Sequence[float]) -> float | None:
        return sum(values) / len(values) if values else None
    return {
        "hit_at_1": average(hit_one),
        "recall_at_1": average(recalls[1]),
        "recall_at_3": average(recalls[3]),
        "recall_at_5": average(recalls[5]),
        "mrr": average(reciprocal_ranks),
        "ndcg": average(ndcgs),
        "irrelevant_memory_rate": _ratio(irrelevant, returned),
        "stale_memory_rate": _ratio(stale, returned),
        "current_truth_correctness": _ratio(sum(current_checks), len(current_checks)),
        "historical_as_of_correctness": _ratio(sum(historical_checks), len(historical_checks)),
        "abstention_correctness": _ratio(sum(abstention_checks), len(abstention_checks)),
        "tenant_leakage": tenant_leakage,
        "user_leakage": user_leakage,
        "forbidden_memory_retrieval_count": forbidden,
        "denominators": {
            "queries": len(materialized),
            "scorable_queries": len(scorable),
            "returned_memories": returned,
            "current_queries": len(current_checks),
            "historical_queries": len(historical_checks),
            "abstention_queries": len(abstention_checks),
        },
    }


def failure_counts(rows: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        for failure in row.get("failures") or []:
            counts[str(failure.get("category") or "unclassified")] += 1
    return dict(sorted(counts.items()))
