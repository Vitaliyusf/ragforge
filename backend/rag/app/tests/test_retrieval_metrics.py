"""Hand-computable tests for the pure IR metrics.

Written before `retrieval_metrics.py` exists. Every expected value below is
derived by hand in the comment beside it, so a failure means the
implementation is wrong rather than that the fixture drifted.
"""
from __future__ import annotations

from math import log2

import pytest

from app.services.retrieval_metrics import (
    dedupe,
    hit_rate_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

PERFECT = ["a", "b", "c"]
RELEVANT = {"a", "b", "c"}


# ── Perfect ranking ───────────────────────────────────────────────────────

def test_perfect_ranking_scores_one_everywhere():
    assert recall_at_k(PERFECT, RELEVANT, 3) == 1.0
    assert precision_at_k(PERFECT, RELEVANT, 3) == 1.0
    assert reciprocal_rank(PERFECT, RELEVANT) == 1.0
    assert ndcg_at_k(PERFECT, RELEVANT, 3) == pytest.approx(1.0)
    assert hit_rate_at_k(PERFECT, RELEVANT, 1) == 1.0


# ── The sole relevant item at rank 3 ──────────────────────────────────────

def test_sole_relevant_at_rank_three():
    """RR is 1/3; nDCG@5 is 1/log2(4) because IDCG is 1 for one relevant."""
    retrieved = ["x", "y", "a", "z", "w"]
    relevant = {"a"}

    assert reciprocal_rank(retrieved, relevant) == pytest.approx(1 / 3)
    # DCG = 1/log2(3+1); IDCG = 1/log2(1+1) = 1.
    assert ndcg_at_k(retrieved, relevant, 5) == pytest.approx(1 / log2(4))
    assert recall_at_k(retrieved, relevant, 5) == 1.0
    assert recall_at_k(retrieved, relevant, 2) == 0.0
    assert precision_at_k(retrieved, relevant, 5) == pytest.approx(0.2)
    assert hit_rate_at_k(retrieved, relevant, 2) == 0.0
    assert hit_rate_at_k(retrieved, relevant, 3) == 1.0


# ── Nothing relevant retrieved ────────────────────────────────────────────

def test_no_relevant_item_retrieved_is_all_zero():
    retrieved = ["x", "y", "z"]
    relevant = {"a", "b"}

    assert recall_at_k(retrieved, relevant, 3) == 0.0
    assert precision_at_k(retrieved, relevant, 3) == 0.0
    assert reciprocal_rank(retrieved, relevant) == 0.0
    assert ndcg_at_k(retrieved, relevant, 3) == 0.0
    assert hit_rate_at_k(retrieved, relevant, 3) == 0.0


# ── k larger than the retrieved list ──────────────────────────────────────

def test_k_beyond_the_retrieved_length_is_well_defined():
    """No padding: precision divides by what was actually returned."""
    retrieved = ["a", "x"]
    relevant = {"a", "b"}

    assert recall_at_k(retrieved, relevant, 50) == 0.5      # 1 of 2 relevant
    assert precision_at_k(retrieved, relevant, 50) == 0.5   # 1 of 2 retrieved
    assert hit_rate_at_k(retrieved, relevant, 50) == 1.0
    # DCG = 1/log2(2) = 1; IDCG over min(2, 50) = 2 ones = 1 + 1/log2(3).
    assert ndcg_at_k(retrieved, relevant, 50) == pytest.approx(
        1.0 / (1.0 + 1.0 / log2(3))
    )


def test_recall_is_not_clamped_to_the_number_of_candidates_returned():
    """A short candidate list reads as a low recall, never as a full one.

    This is the convention the eval harness depends on: if retrieval returns
    six chunks, Recall@20 must still divide by the ground truth and report
    the miss, rather than quietly rescoring itself as Recall@6.
    """
    retrieved = ["x", "y", "z", "a", "w", "v"]
    relevant = {"a", "b"}

    assert recall_at_k(retrieved, relevant, 20) == 0.5
    assert recall_at_k(retrieved, relevant, 6) == 0.5
    assert recall_at_k(retrieved, relevant, 3) == 0.0


def test_empty_retrieved_list_is_zero_not_an_error():
    assert recall_at_k([], {"a"}, 5) == 0.0
    assert precision_at_k([], {"a"}, 5) == 0.0
    assert reciprocal_rank([], {"a"}) == 0.0
    assert ndcg_at_k([], {"a"}, 5) == 0.0
    assert hit_rate_at_k([], {"a"}, 5) == 0.0


@pytest.mark.parametrize("k", [0, -1])
def test_non_positive_k_is_zero_not_an_error(k):
    assert recall_at_k(PERFECT, RELEVANT, k) == 0.0
    assert precision_at_k(PERFECT, RELEVANT, k) == 0.0
    assert ndcg_at_k(PERFECT, RELEVANT, k) == 0.0
    assert hit_rate_at_k(PERFECT, RELEVANT, k) == 0.0


# ── Empty relevant set ────────────────────────────────────────────────────

def test_empty_relevant_set_returns_zero_for_the_runner_to_exclude():
    """0.0 here is a sentinel, not a judgment.

    An unlabelled item has no measurable score. The functions stay total and
    return 0.0; `eval_runner` excludes such items from the mean and reports
    them as `items_skipped`, so a half-labelled dataset is visible rather
    than quietly depressing every average.
    """
    assert recall_at_k(PERFECT, set(), 3) == 0.0
    assert precision_at_k(PERFECT, set(), 3) == 0.0
    assert reciprocal_rank(PERFECT, set()) == 0.0
    assert ndcg_at_k(PERFECT, set(), 3) == 0.0
    assert hit_rate_at_k(PERFECT, set(), 3) == 0.0


# ── Duplicates ────────────────────────────────────────────────────────────

def test_duplicates_are_removed_preserving_first_occurrence():
    assert dedupe(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]


def test_duplicates_do_not_inflate_precision_or_shift_rank():
    """A retriever returning "a" three times has found one relevant chunk."""
    retrieved = ["a", "a", "a", "b"]
    relevant = {"a", "b"}

    # After dedupe the list is ["a", "b"]: both relevant, both in the top 2.
    assert precision_at_k(retrieved, relevant, 4) == 1.0
    assert recall_at_k(retrieved, relevant, 2) == 1.0
    assert ndcg_at_k(retrieved, relevant, 4) == pytest.approx(1.0)


def test_duplicates_after_a_miss_do_not_change_the_rank_of_the_first_hit():
    retrieved = ["x", "x", "a"]
    relevant = {"a"}

    # Deduped to ["x", "a"], so the first hit is at rank 2, not rank 3.
    assert reciprocal_rank(retrieved, relevant) == pytest.approx(0.5)
