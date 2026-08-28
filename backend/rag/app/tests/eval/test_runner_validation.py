"""Stale-label validation performed before a run is allowed to score."""
from __future__ import annotations

from typing import Any, Dict

import pytest

from app.services.eval_runner import (
    MATCH_CHUNK,
    MATCH_FILE,
    MATCH_MIXED,
    STALE_POLICY_FAIL,
    STALE_POLICY_UNSCORABLE,
    classify_labels,
    label_targets,
    stale_label_policy,
)
from app.services.eval_store import EvalStore

from app.tests.eval._harness import (
    FakeBackend,
    build,
    build_config,
    execute,
    fetch,
)

def validation(store: EvalStore, run_id: str) -> Dict[str, Any]:
    return fetch(store, run_id)["label_validation"]


def test_a_deleted_chunk_label_fails_the_run_before_anything_is_scored():
    """Fail-fast is the default: a rotted golden set measures nothing."""
    backend = FakeBackend(index={"c1"})
    store, runner, backend, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])

    assert stored["status"] == "failed"
    assert "no longer exist" in stored["error"]
    # Nothing was retrieved, so nothing was scored against a dead label.
    assert backend.calls == []
    assert stored["per_item"] == []


def test_the_refused_run_stores_the_counts_and_the_affected_item():
    backend = FakeBackend(index={"c1"})
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    report = validation(store, run["run_id"])

    assert report["checked"] is True
    assert report["stale_label_count"] == 1
    assert report["stale_item_count"] == 1
    assert report["stale_ids"] == ["c9"]
    assert len(report["stale_item_ids"]) == 1
    assert report["policy"] == STALE_POLICY_FAIL


def test_stale_labels_are_never_scored_as_retrieval_misses():
    """The bug this feature exists to prevent, under the lenient policy."""
    backend = FakeBackend(index={"c1"})
    store, runner, _, dataset_id = build(
        backend=backend, eval_stale_label_policy=STALE_POLICY_UNSCORABLE
    )
    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    results = stored["results"]

    assert stored["status"] == "completed"
    # One item was scorable and its label ranked first. Counting the stale
    # item as a miss would have reported Recall@10 of 0.5.
    assert results["items_evaluated"] == 1
    assert results["items_unscorable"] == 1
    assert results["recall_at_k"]["10"] == pytest.approx(1.0)
    assert results["mrr"] == pytest.approx(1.0)


def test_an_unscorable_item_is_marked_and_never_retrieved():
    backend = FakeBackend(index={"c1"})
    store, runner, backend, dataset_id = build(
        backend=backend, eval_stale_label_policy=STALE_POLICY_UNSCORABLE
    )
    run = execute(runner, dataset_id)
    rows = {row["query"]: row for row in fetch(store, run["run_id"])["per_item"]}

    assert rows["third"]["unscorable"] is True
    assert rows["third"]["skipped"] is False
    assert rows["third"].get("scores") is None
    assert rows["first"]["unscorable"] is False
    # Only the scorable item cost an embed call.
    assert [call["query"] for call in backend.calls] == ["first"]


def test_a_label_present_but_barred_from_retrieval_is_reported_separately():
    """"Deleted" and "suppressed" call for different fixes."""
    backend = FakeBackend(index={"c1", "c9"}, barred={"c9"})
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    report = validation(store, run["run_id"])

    assert report["stale_label_count"] == 0
    assert report["unretrievable_label_count"] == 1
    assert report["unretrievable_ids"] == ["c9"]
    assert report["unscorable_item_count"] == 1
    assert fetch(store, run["run_id"])["status"] == "failed"


def test_a_fully_valid_golden_set_runs_and_records_a_clean_check():
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])

    assert stored["status"] == "completed"
    assert stored["label_validation"]["checked"] is True
    assert stored["label_validation"]["stale_label_count"] == 0
    assert stored["label_validation"]["labels_checked"] == 2
    assert stored["results"]["items_unscorable"] == 0


def test_file_level_labels_are_verified_too():
    backend = FakeBackend(
        {"only": {"chunks": [{"file_id": "f1"}]}}, index={"f1"}
    )
    store, runner, _, dataset_id = build(
        items=[
            {"query": "only", "relevant_file_ids": ["f1"]},
            {"query": "gone", "relevant_file_ids": ["f-dropped"]},
        ],
        backend=backend,
    )
    run = execute(runner, dataset_id)
    report = validation(store, run["run_id"])

    assert backend.verify_calls[0]["file_ids"] == ["f-dropped", "f1"]
    assert report["stale_ids"] == ["f-dropped"]
    assert fetch(store, run["run_id"])["status"] == "failed"


def test_verification_asks_only_about_the_ids_the_run_will_score():
    """A mixed item scored on its chunk ids must not be checked on its file ids."""
    backend = FakeBackend({"both": {"chunks": [{"chunk_id": "c1"}]}})
    store, runner, backend, dataset_id = build(
        items=[
            # Labelled at both granularities: mixed mode scores it on the
            # finer one, so `f1` is never a label this run can miss.
            {"query": "both", "relevant_chunk_ids": ["c1"], "relevant_file_ids": ["f1"]},
            {"query": "chunk only", "relevant_chunk_ids": ["c2"]},
            {"query": "file only", "relevant_file_ids": ["f2"]},
        ],
        backend=backend,
    )
    execute(runner, dataset_id)

    assert backend.verify_calls[0]["chunk_ids"] == ["c1", "c2"]
    assert backend.verify_calls[0]["file_ids"] == ["f2"]


def test_labels_that_could_not_be_verified_leave_a_warning_not_a_silent_pass():
    """An unreachable vector_db must not read as "no stale labels"."""
    backend = FakeBackend(verify_error="vector_db unavailable")
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    report = stored["label_validation"]

    assert stored["status"] == "completed"
    assert report["checked"] is False
    assert report["reason"] == "unavailable"
    assert "vector_db unavailable" in report["error"]
    # None, not 0: nothing was measured, so no count may be claimed.
    assert report["stale_label_count"] is None


def test_validation_can_be_switched_off_and_says_so():
    store, runner, backend, dataset_id = build(eval_validate_labels=False)
    run = execute(runner, dataset_id)
    report = validation(store, run["run_id"])

    assert backend.verify_calls == []
    assert report["checked"] is False
    assert report["reason"] == "disabled"


def test_an_unknown_policy_falls_back_to_failing_rather_than_to_scoring():
    """A typo must not become the permissive branch."""
    assert stale_label_policy(build_config(eval_stale_label_policy="nonsense")) == (
        STALE_POLICY_FAIL
    )

    backend = FakeBackend(index={"c1"})
    store, runner, _, dataset_id = build(
        backend=backend, eval_stale_label_policy="nonsense"
    )
    run = execute(runner, dataset_id)

    assert fetch(store, run["run_id"])["status"] == "failed"


def test_label_targets_splits_ids_by_the_mode_each_item_is_scored_under():
    items = [
        {"query": "a", "relevant_chunk_ids": ["c1"], "relevant_file_ids": ["f1"]},
        {"query": "b", "relevant_file_ids": ["f2"]},
    ]

    assert label_targets(items, MATCH_MIXED) == ({"c1"}, {"f2"})
    assert label_targets(items, MATCH_FILE) == (set(), {"f1", "f2"})
    assert label_targets(items, MATCH_CHUNK) == ({"c1"}, set())


def test_classify_caps_the_reported_ids_but_never_the_counts():
    """A wholly stale dataset must not write its entire label set into the run."""
    items = [
        {"item_id": f"i{index}", "query": "q", "relevant_chunk_ids": [f"c{index}"]}
        for index in range(10)
    ]
    verified = {
        "chunk_ids": {
            "present": [],
            "retrievable": [],
            "missing": [f"c{index}" for index in range(10)],
        },
        "file_ids": {"present": [], "retrievable": [], "missing": []},
    }

    report = classify_labels(items, MATCH_CHUNK, verified, max_reported_ids=3)

    assert report.summary["stale_label_count"] == 10
    assert report.summary["stale_item_count"] == 10
    assert len(report.summary["stale_ids"]) == 3
    assert report.summary["truncated"] is True
    # The full set still drives which items are excluded from scoring.
    assert len(report.unscorable) == 10

