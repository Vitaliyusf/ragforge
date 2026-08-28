"""Retrieval scoring: aggregates, rank depth, eligibility and per-dataset label modes."""
from __future__ import annotations


import pytest

from app.services.eval_runner import (
    K_VALUES,
    MATCH_CHUNK,
    MATCH_FILE,
    MATCH_MIXED,
    aggregate,
    candidate_depth,
    dataset_match_mode,
    eligible_chunks,
    relevant_ids,
    retrieved_ids,
)

from app.tests.eval._harness import (
    FakeBackend,
    build,
    build_config,
    execute,
    fetch,
)

def test_aggregate_scores_match_the_known_orderings():
    """Relevant chunk at rank 1 and rank 3: MRR = (1 + 1/3) / 2."""
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    results = fetch(store, run["run_id"])["results"]

    assert results["items_evaluated"] == 2
    assert results["items_skipped"] == 0
    assert results["items_failed"] == 0
    assert results["mrr"] == pytest.approx((1 + 1 / 3) / 2)
    assert results["recall_at_k"]["1"] == pytest.approx(0.5)
    assert results["recall_at_k"]["3"] == pytest.approx(1.0)
    assert results["hit_rate_at_k"]["1"] == pytest.approx(0.5)
    assert results["hit_rate_at_k"]["3"] == pytest.approx(1.0)


def test_eval_searches_run_in_the_eval_traffic_class():
    _, runner, backend, dataset_id = build()
    execute(runner, dataset_id)

    assert [call["traffic_class"] for call in backend.calls] == ["eval", "eval"]


def test_the_run_records_where_the_first_hit_landed_per_item():
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    rows = {row["query"]: row for row in fetch(store, run["run_id"])["per_item"]}

    assert rows["first"]["first_hit_rank"] == 1
    assert rows["third"]["first_hit_rank"] == 3
    assert rows["third"]["reciprocal_rank"] == pytest.approx(1 / 3)



def test_retrieval_is_tagged_as_an_eval_sweep_and_carries_the_tenant():
    store, runner, backend, dataset_id = build()
    execute(runner, dataset_id)

    assert {call["pass_name"] for call in backend.calls} == {"eval"}
    assert {call["tenant"] for call in backend.calls} == {"tenant-a"}


# ── Candidate depth ───────────────────────────────────────────────────────

def test_eval_retrieval_asks_for_every_rank_it_reports():
    """Recall@20 over six candidates would be Recall@6 under another name."""
    store, runner, backend, dataset_id = build()
    execute(runner, dataset_id)

    assert 20 in K_VALUES
    assert {call["top_k"] for call in backend.calls} == {20}


def test_candidate_depth_is_floored_at_the_largest_reported_k():
    """A depth below max(K_VALUES) is a k the run could never observe."""
    assert candidate_depth(build_config(eval_candidate_k=5)) == max(K_VALUES)
    assert candidate_depth(build_config(eval_candidate_k=50)) == 50

    store, runner, backend, dataset_id = build(eval_candidate_k=5)
    execute(runner, dataset_id)

    assert {call["top_k"] for call in backend.calls} == {max(K_VALUES)}


def test_recall_at_twenty_can_see_a_hit_below_the_production_top_k():
    """The bug this guards: a rank-12 hit scored 0.0 at every k above 6."""
    deep = ["c%d" % index for index in range(1, 21)]
    backend = FakeBackend({"deep": {"chunks": [{"chunk_id": cid} for cid in deep]}})
    store, runner, _, dataset_id = build(
        items=[{"query": "deep", "relevant_chunk_ids": ["c12"]}],
        backend=backend,
    )
    run = execute(runner, dataset_id)
    results = fetch(store, run["run_id"])["results"]

    assert results["recall_at_k"]["20"] == 1.0
    assert results["recall_at_k"]["10"] == 0.0
    assert results["mrr"] == pytest.approx(1 / 12)



def test_a_fully_chunk_labelled_dataset_matches_on_chunk_id():
    assert dataset_match_mode([{"relevant_chunk_ids": ["c"]}]) == MATCH_CHUNK


def test_a_file_only_dataset_falls_back_to_file_id():
    assert dataset_match_mode([{"relevant_file_ids": ["f"]}]) == MATCH_FILE


def test_an_inconsistently_labelled_dataset_is_marked_mixed():
    """Scoring half the items against the wrong id field would be silent
    nonsense, so the run says `mixed` and each row records its own mode."""
    items = [{"relevant_chunk_ids": ["c"]}, {"relevant_file_ids": ["f"]}]
    assert dataset_match_mode(items) == MATCH_MIXED


def test_mixed_mode_prefers_chunk_ids_per_item():
    item = {"relevant_chunk_ids": ["c"], "relevant_file_ids": ["f"]}
    assert relevant_ids(item, MATCH_MIXED) == {"c"}


def test_file_mode_scores_against_file_ids():
    backend = FakeBackend(
        responses={"by file": {"chunks": [{"chunk_id": "c1", "file_id": "f9"}]}}
    )
    store, runner, _, dataset_id = build(
        items=[{"query": "by file", "relevant_file_ids": ["f9"]}], backend=backend
    )
    run = execute(runner, dataset_id)
    fetched = fetch(store, run["run_id"])

    assert fetched["match_mode"] == MATCH_FILE
    assert fetched["results"]["hit_rate_at_k"]["1"] == pytest.approx(1.0)


# ── Response parsing ──────────────────────────────────────────────────────

def test_chunks_the_app_would_refuse_to_use_are_not_scored():
    """Scoring filtered-out chunks would measure a retriever that does not
    exist — the policy gate is part of the retrieval being evaluated."""
    response = {
        "chunks": [
            {"chunk_id": "keep"},
            {"chunk_id": "removed", "review_status": "removed"},
            {"chunk_id": "blocked", "retrieval_allowed": False},
        ]
    }
    assert retrieved_ids(eligible_chunks(response), MATCH_CHUNK) == ["keep"]


def test_the_qdrant_nested_payload_shape_is_understood():
    response = {"chunks": [{"payload": {"chunk_id": "nested", "review_status": "clean"}}]}
    assert retrieved_ids(eligible_chunks(response), MATCH_CHUNK) == ["nested"]


def test_file_mode_falls_back_to_document_id():
    response = {"chunks": [{"chunk_id": "c1", "document_id": "d1"}]}
    assert retrieved_ids(eligible_chunks(response), MATCH_FILE) == ["d1"]


# ── Aggregation ───────────────────────────────────────────────────────────

def test_unlabelled_items_are_excluded_from_the_means_and_counted():
    """A half-labelled dataset must show as a small denominator, never as a
    retrieval regression."""
    rows = [
        {
            "reciprocal_rank": 1.0,
            "latency_ms": 10.0,
            "scores": {
                "recall_at_k": {str(k): 1.0 for k in (1, 3, 5, 10, 20)},
                "precision_at_k": {str(k): 1.0 for k in (1, 3, 5, 10, 20)},
                "hit_rate_at_k": {str(k): 1.0 for k in (1, 3, 5, 10, 20)},
                "ndcg_at_k": {str(k): 1.0 for k in (1, 3, 5, 10, 20)},
            },
        },
        {"skipped": True, "latency_ms": 5.0},
    ]
    results = aggregate(rows)

    assert results["items_evaluated"] == 1
    assert results["items_skipped"] == 1
    assert results["recall_at_k"]["5"] == pytest.approx(1.0)
    assert results["mean_latency_ms"] == pytest.approx(7.5)


def test_a_run_with_nothing_scorable_reports_none_not_zero():
    """A mean over nothing is unknown. "Recall@5: 0%" would be a lie."""
    results = aggregate([{"skipped": True}])

    assert results["mrr"] is None
    assert results["recall_at_k"]["5"] is None
    assert results["items_evaluated"] == 0


# ── end_to_end mode ───────────────────────────────────────────────────────


