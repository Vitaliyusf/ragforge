"""Tests for deterministic stage attribution over eval items.

Every category is exercised from a trace built with the real
:class:`RetrievalTrace` collector rather than a hand-written dict: an
attribution derived from a shape the collector cannot actually produce would
pass here and classify nothing in production.

Three things are asserted: that each deterministic category is reached only
by its own evidence; that missing evidence yields ``unclassified`` instead of
a guess; and that a run's aggregate agrees with the rows beneath it.

Async tests drive ``asyncio.run`` from sync functions, matching
``test_eval_runner.py``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.services.failure_attribution import (
    CATEGORY_COMPLETENESS,
    CATEGORY_CONTEXT,
    CATEGORY_GENERATION,
    CATEGORY_GROUNDING,
    CATEGORY_INDEX,
    CATEGORY_NONE,
    CATEGORY_NOT_APPLICABLE,
    CATEGORY_PASS_TWO,
    CATEGORY_PIPELINE_ERROR,
    CATEGORY_RANKING,
    CATEGORY_RETRIEVAL,
    CATEGORY_STALE_LABELS,
    CATEGORY_UNCLASSIFIED,
    FAILURE_CATEGORIES,
    REASON_ANSWER_UNJUDGED,
    REASON_NO_TRACE,
    REASON_TRUNCATED_CANDIDATES,
    aggregate_attribution,
    classify_item,
)
from app.services.benchmark_runner import PHASE_RETRIEVAL_BASE
from app.services.retrieval_trace import (
    DROP_RETRIEVAL_NOT_ALLOWED,
    STAGE_BASE,
    STAGE_FINAL_CONTEXT,
    STAGE_PASS_ONE,
    STAGE_PASS_TWO,
    RetrievalTrace,
)
from app.tests.test_benchmark_runner import (
    build as build_benchmark,
    fetch as fetch_benchmark,
    phases_by_name,
    run_benchmark,
)
from app.tests.test_eval_runner import FakeBackend, build, execute, fetch


def chunk(chunk_id: str, *, file_id: str = "f1", score: float = 0.8) -> Dict[str, Any]:
    return {"chunk_id": chunk_id, "file_id": file_id, "score": score}


def row(
    *,
    expected: Optional[List[str]] = None,
    retrieved: Optional[List[str]] = None,
    trace: Optional[RetrievalTrace] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """One item row in the shape ``eval_runner`` stores it."""
    built: Dict[str, Any] = {
        "item_id": "item-1",
        "query": "what is the policy",
        "expected_ids": list(expected or []),
        "retrieved_ids": list(retrieved or []),
        "skipped": not expected,
        "unscorable": False,
        "error": None,
    }
    if trace is not None:
        built["retrieval_trace"] = trace.to_payload()
    built.update(fields)
    return built


def category(item: Dict[str, Any]) -> str:
    return classify_item(item)["category"]


# ── Not failures ──────────────────────────────────────────────────────────

def test_an_unlabelled_item_is_not_attributed():
    """It had no expectation, so it cannot have failed one."""
    verdict = classify_item(row())

    assert verdict["category"] == CATEGORY_NOT_APPLICABLE


def test_a_retrieved_item_in_a_retrieval_run_has_no_failure():
    """A retrieval run holds no answer evidence and must invent none."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1")], returned_count=1)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    assert category(row(expected=["c1"], retrieved=["c1"], trace=trace)) == CATEGORY_NONE


def test_stale_labels_are_a_dataset_state_not_a_retrieval_failure():
    """An unscorable item is never retrieved for, so no stage lost it."""
    verdict = classify_item(row(expected=["c1"], unscorable=True))

    assert verdict["category"] == CATEGORY_STALE_LABELS
    assert verdict["evidence"]["reason"] == "labels_unreachable"


def test_a_raised_item_reports_where_its_trace_stopped():
    """The stage it died on is the most useful thing it can still report."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1")], returned_count=1)

    verdict = classify_item(
        row(expected=["c9"], trace=trace, error="embedding unavailable")
    )

    assert verdict["category"] == CATEGORY_PIPELINE_ERROR
    assert verdict["evidence"] == {"stages_recorded": 1, "last_stage": STAGE_BASE}


# ── Retrieval-side categories ─────────────────────────────────────────────

def test_an_empty_index_is_not_reported_as_a_ranking_problem():
    """Nothing was returned to rank, so no ranking decision lost anything."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [], returned_count=0)
    trace.record_stage(STAGE_FINAL_CONTEXT, [])

    verdict = classify_item(row(expected=["c9"], trace=trace))

    assert verdict["category"] == CATEGORY_INDEX
    assert verdict["evidence"]["stages_searched"] == 1


def test_a_labelled_chunk_that_was_never_a_candidate_is_a_retrieval_failure():
    """Candidates came back, the labelled one was not among them."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1"), chunk("c2")], returned_count=2)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1"), chunk("c2")])

    verdict = classify_item(row(expected=["c9"], retrieved=["c1", "c2"], trace=trace))

    assert verdict["category"] == CATEGORY_RETRIEVAL
    assert verdict["evidence"]["missing_ids"] == ["c9"]
    assert verdict["evidence"]["candidates_returned"] == 2


def test_a_candidate_that_did_not_reach_the_context_is_a_ranking_failure():
    """It was retrieved and then demoted out of the scored window."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1"), chunk("c9")], returned_count=2)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    verdict = classify_item(row(expected=["c9"], retrieved=["c1"], trace=trace))

    assert verdict["category"] == CATEGORY_RANKING
    assert verdict["evidence"]["candidate_stages"] == [STAGE_BASE]


def test_a_skipped_second_pass_is_attributed_to_the_branch_that_skipped_it():
    """The pass that could have found it never ran; that is the failure."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_PASS_ONE, [chunk("c1")], returned_count=1)
    trace.record_decision(
        STAGE_PASS_TWO,
        "skipped",
        reason="sufficient_pass_one",
        detail={"top_score": 0.91},
    )
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    verdict = classify_item(row(expected=["c9"], retrieved=["c1"], trace=trace))

    assert verdict["category"] == CATEGORY_PASS_TWO
    assert verdict["evidence"]["skip_reason"] == "sufficient_pass_one"
    assert verdict["evidence"]["top_score"] == pytest.approx(0.91)


def test_a_second_pass_that_ran_leaves_the_failure_with_retrieval():
    """Both passes searched and neither produced it — not a branch problem."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_PASS_ONE, [chunk("c1")], returned_count=1)
    trace.record_decision(STAGE_PASS_TWO, "triggered", reason="low_top_score")
    trace.record_stage(STAGE_PASS_TWO, [chunk("c2")], returned_count=1)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1"), chunk("c2")])

    assert category(row(expected=["c9"], retrieved=["c1", "c2"], trace=trace)) == (
        CATEGORY_RETRIEVAL
    )


def test_a_barred_candidate_is_a_context_failure_not_a_retrieval_one():
    """"Retrieved then refused" and "never found" score alike and differ."""
    trace = RetrievalTrace()
    trace.record_stage(
        STAGE_BASE,
        [chunk("c1")],
        returned_count=2,
        dropped=[{"chunk_id": "c9", "reason": DROP_RETRIEVAL_NOT_ALLOWED}],
    )
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    verdict = classify_item(row(expected=["c9"], retrieved=["c1"], trace=trace))

    assert verdict["category"] == CATEGORY_CONTEXT
    assert verdict["evidence"]["drop_reasons"] == [DROP_RETRIEVAL_NOT_ALLOWED]


def test_a_partial_hit_is_a_completeness_failure():
    """One labelled id landed and one did not: the stage worked, once."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1")], returned_count=1)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    verdict = classify_item(
        row(expected=["c1", "c9"], retrieved=["c1"], trace=trace)
    )

    assert verdict["category"] == CATEGORY_COMPLETENESS
    assert verdict["evidence"]["missing_ids"] == ["c9"]
    assert verdict["evidence"]["retrieved_expected_count"] == 1


def test_a_file_level_label_matches_on_the_candidate_file_id():
    """A file-labelled dataset is scored on file ids, so evidence uses them."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1", file_id="f9")], returned_count=1)
    trace.record_stage(STAGE_FINAL_CONTEXT, [])

    assert category(row(expected=["f9"], trace=trace)) == CATEGORY_RANKING


# ── Answer-side categories ────────────────────────────────────────────────

def test_an_empty_answer_over_correct_context_is_a_generation_failure():
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1")], returned_count=1)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    verdict = classify_item(
        row(expected=["c1"], retrieved=["c1"], trace=trace, answer="")
    )

    assert verdict["category"] == CATEGORY_GENERATION
    assert verdict["evidence"]["reason"] == "empty_answer"


def test_an_unsupported_answer_over_correct_context_is_a_grounding_failure():
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1")], returned_count=1)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    verdict = classify_item(
        row(
            expected=["c1"],
            retrieved=["c1"],
            trace=trace,
            answer="The policy allows it.",
            hallucination_verdict="severe",
            unsupported_claim_count=2,
        )
    )

    assert verdict["category"] == CATEGORY_GROUNDING
    assert verdict["evidence"]["hallucination_verdict"] == "severe"


def test_a_judged_clean_answer_is_not_a_failure():
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1")], returned_count=1)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    assert category(
        row(
            expected=["c1"],
            retrieved=["c1"],
            trace=trace,
            answer="Yes.",
            hallucination_verdict="none",
        )
    ) == CATEGORY_NONE


# ── Insufficient evidence ─────────────────────────────────────────────────

def test_a_miss_without_a_trace_is_unclassified():
    """No lineage, no attribution. The score alone blames no stage."""
    verdict = classify_item(row(expected=["c9"], retrieved=["c1"]))

    assert verdict["category"] == CATEGORY_UNCLASSIFIED
    assert verdict["evidence"]["reason"] == REASON_NO_TRACE


def test_a_truncated_candidate_list_cannot_prove_a_chunk_was_never_a_candidate():
    """Absence from a list that was cut short is not evidence of absence."""
    trace = RetrievalTrace(max_candidates=1)
    trace.record_stage(STAGE_BASE, [chunk("c1"), chunk("c2")], returned_count=2)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    verdict = classify_item(row(expected=["c9"], retrieved=["c1"], trace=trace))

    assert verdict["category"] == CATEGORY_UNCLASSIFIED
    assert verdict["evidence"]["reason"] == REASON_TRUNCATED_CANDIDATES


def test_a_long_query_alone_does_not_make_an_item_unclassified():
    """The trace's truncation flag also fires for the query, which is not
    evidence about candidates."""
    trace = RetrievalTrace(max_query_chars=4)
    trace.record_stage(
        STAGE_BASE, [chunk("c1")], query="a much longer question", returned_count=1
    )
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    assert trace.truncated is True
    assert category(row(expected=["c9"], retrieved=["c1"], trace=trace)) == (
        CATEGORY_RETRIEVAL
    )


def test_an_unjudged_answer_is_unclassified_not_a_pass():
    """The judge did not return; whether the answer held up is unknown."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [chunk("c1")], returned_count=1)
    trace.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    verdict = classify_item(
        row(
            expected=["c1"],
            retrieved=["c1"],
            trace=trace,
            answer="Yes.",
            hallucination_verdict=None,
        )
    )

    assert verdict["category"] == CATEGORY_UNCLASSIFIED
    assert verdict["evidence"]["reason"] == REASON_ANSWER_UNJUDGED


def test_evidence_carries_no_query_or_chunk_text():
    """Item rows are read by every admin of the tenant."""
    trace = RetrievalTrace()
    trace.record_stage(
        STAGE_BASE,
        [{"chunk_id": "c1", "text": "salary is 120000"}],
        query="what is the salary",
        returned_count=1,
    )

    evidence = classify_item(
        row(expected=["c9"], query="what is the salary", trace=trace)
    )["evidence"]

    serialized = repr(evidence)
    assert "salary" not in serialized
    assert "120000" not in serialized


# ── Aggregation ───────────────────────────────────────────────────────────

def missing_row(item_id: str, trace: RetrievalTrace) -> Dict[str, Any]:
    return row(expected=["c9"], retrieved=["c1"], trace=trace, item_id=item_id)


def test_the_aggregate_counts_every_category_and_excludes_unlabelled_items():
    empty = RetrievalTrace()
    empty.record_stage(STAGE_BASE, [], returned_count=0)
    ranked = RetrievalTrace()
    ranked.record_stage(STAGE_BASE, [chunk("c1"), chunk("c9")], returned_count=2)
    ranked.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])
    hit = RetrievalTrace()
    hit.record_stage(STAGE_BASE, [chunk("c1")], returned_count=1)
    hit.record_stage(STAGE_FINAL_CONTEXT, [chunk("c1")])

    summary = aggregate_attribution(
        [
            missing_row("item-1", empty),
            missing_row("item-2", ranked),
            row(expected=["c1"], retrieved=["c1"], trace=hit, item_id="item-3"),
            row(item_id="item-4"),
        ]
    )

    assert summary["counts"][CATEGORY_INDEX] == 1
    assert summary["counts"][CATEGORY_RANKING] == 1
    assert summary["items_attributed"] == 3
    assert summary["items_without_failure"] == 1
    assert summary["items_failed_attributed"] == 2
    assert summary["items_unclassified"] == 0
    assert summary["rates"][CATEGORY_INDEX] == pytest.approx(1 / 3)
    assert set(summary["counts"]) == set(FAILURE_CATEGORIES)


def test_rates_are_null_when_nothing_could_be_attributed():
    """A run with no labelled items has no measured rates, not 0%."""
    summary = aggregate_attribution([row(), row()])

    assert summary["items_attributed"] == 0
    assert all(value is None for value in summary["rates"].values())


def test_the_aggregate_reuses_the_verdict_already_stored_on_the_row():
    """The summary and the drill-down must never disagree."""
    stored = row(expected=["c9"], retrieved=["c1"])
    stored["failure_attribution"] = {"category": CATEGORY_CONTEXT, "evidence": {}}

    summary = aggregate_attribution([stored])

    assert summary["counts"][CATEGORY_CONTEXT] == 1
    assert summary["counts"][CATEGORY_UNCLASSIFIED] == 0


# ── Through a real run ────────────────────────────────────────────────────

def test_a_run_attributes_its_items_and_carries_the_counts_in_its_results():
    """End to end: one item hits, one is barred by the eligibility gate."""
    backend = FakeBackend(
        responses={
            "first": {"chunks": [{"chunk_id": "c1", "text": "a"}]},
            "barred": {
                "chunks": [
                    {"chunk_id": "c1", "text": "a"},
                    {"chunk_id": "c9", "text": "b", "retrieval_allowed": False},
                ]
            },
        }
    )
    store, runner, _, dataset_id = build(
        items=[
            {"query": "first", "relevant_chunk_ids": ["c1"]},
            {"query": "barred", "relevant_chunk_ids": ["c9"]},
        ],
        backend=backend,
    )

    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    by_query = {item["query"]: item for item in stored["per_item"]}

    assert by_query["first"]["failure_attribution"]["category"] == CATEGORY_NONE
    barred = by_query["barred"]["failure_attribution"]
    assert barred["category"] == CATEGORY_CONTEXT
    assert barred["evidence"]["missing_ids"] == ["c9"]

    summary = stored["results"]["failure_attribution"]
    assert summary["counts"][CATEGORY_CONTEXT] == 1
    assert summary["items_attributed"] == 2
    assert summary["items_without_failure"] == 1


def test_a_failed_item_is_attributed_to_the_pipeline_not_to_retrieval():
    """An embedding outage must not read as a retrieval quality regression."""
    backend = FakeBackend(fail_queries={"third"})
    store, runner, _, dataset_id = build(backend=backend)

    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    summary = stored["results"]["failure_attribution"]

    assert summary["counts"][CATEGORY_PIPELINE_ERROR] == 1
    assert summary["counts"][CATEGORY_RETRIEVAL] == 0


def test_a_benchmark_phase_carries_the_attribution_of_its_own_run():
    """A phase stores an eval run's results, so it needs no second path."""
    store, orchestrator, _, dataset_id = build_benchmark()

    benchmark = fetch_benchmark(
        store, run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])["benchmark_id"]
    )
    summary = phases_by_name(benchmark)[PHASE_RETRIEVAL_BASE]["results"][
        "failure_attribution"
    ]

    assert summary["items_attributed"] == 2
    assert summary["items_without_failure"] == 2
    assert summary["items_failed_attributed"] == 0
