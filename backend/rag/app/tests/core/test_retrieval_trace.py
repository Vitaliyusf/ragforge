"""Tests for per-item retrieval diagnostics.

Three things are being asserted, in increasing scope: that a trace records
only ids, ranks and scores under its bounds; that a retrieval eval item's row
carries the lineage explaining its score; and that a full extended turn's
trace explains one chunk's movement from the pass it entered on to the
context the answer was generated from.

Async tests drive ``asyncio.run`` from sync functions, matching
``test_rag.py`` and ``test_eval_runner.py``.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from app.services.conversation_events import CollectingConversationEmitter
from app.services.eval_runner import MODE_END_TO_END, partition_eligible
from app.services.retrieval_trace import (
    DROP_RETRIEVAL_NOT_ALLOWED,
    DROP_REVIEW_REMOVED,
    STAGE_BASE,
    STAGE_FINAL_CONTEXT,
    STAGE_MERGED,
    STAGE_PASS_ONE,
    STAGE_PASS_TWO,
    RetrievalTrace,
)
from app.tests.eval._harness import ADMIN, FakeBackend, build, execute, fetch
from app.tests._service_harness import TEST_IDENTITY, build_service
from shared.context import bound_context


def stages_by_name(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The first recorded stage under each name.

    Pass one records one stage per query it ran — the rewrite and then each
    subquery — so a name can legitimately appear more than once.
    """
    found: Dict[str, Dict[str, Any]] = {}
    for stage in payload["stages"]:
        found.setdefault(stage["stage"], stage)
    return found


# ── The collector's own bounds ────────────────────────────────────────────

def test_a_candidate_carries_no_chunk_text():
    """The one bound that is a security property, not a size preference."""
    trace = RetrievalTrace()
    trace.record_stage(
        STAGE_BASE,
        [{"chunk_id": "c1", "file_id": "f1", "score": 0.8, "text": "salary is 120000"}],
    )

    payload = trace.to_payload()

    assert payload["stages"][0]["candidates"] == [
        {"rank": 1, "chunk_id": "c1", "file_id": "f1", "score": 0.8}
    ]
    assert "salary" not in json.dumps(payload)


def test_a_candidate_is_read_from_the_nested_payload_shape():
    """Qdrant nests what the flat shape puts at the top level."""
    trace = RetrievalTrace()
    trace.record_stage(
        STAGE_BASE,
        [{"score": 0.4, "payload": {"chunk_id": "c1", "metadata": {"file_id": "f1"}}}],
    )

    assert trace.stages[0]["candidates"] == [
        {"rank": 1, "chunk_id": "c1", "file_id": "f1", "score": 0.4}
    ]


def test_a_missing_score_stays_none():
    """An unmeasured score must not read as a perfectly bad one."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_BASE, [{"chunk_id": "c1"}])

    assert trace.stages[0]["candidates"][0]["score"] is None


def test_a_candidate_keeps_bounded_hybrid_arm_diagnostics_without_text():
    trace = RetrievalTrace()
    trace.record_stage(
        STAGE_BASE,
        [
            {
                "chunk_id": "c1",
                "score": 0.03,
                "retrieval_diagnostics": {
                    "dense_rank": 4,
                    "dense_score": 0.71,
                    "sparse_rank": 1,
                    "sparse_score": 8.2,
                    "fused_rank": 1,
                    "fused_score": 0.03,
                    "matched_arms": ["dense", "sparse"],
                    "text": "must never escape",
                },
            }
        ],
    )

    candidate = trace.stages[0]["candidates"][0]
    assert candidate["retrieval"] == {
        "dense_rank": 4,
        "dense_score": 0.71,
        "sparse_rank": 1,
        "sparse_score": 8.2,
        "fused_rank": 1,
        "fused_score": 0.03,
        "matched_arms": ["dense", "sparse"],
    }
    assert "must never escape" not in json.dumps(candidate)


def test_a_truncated_candidate_list_says_so():
    """A silently shortened lineage reads as 'never a candidate'."""
    trace = RetrievalTrace(max_candidates=2)
    trace.record_stage(STAGE_BASE, [{"chunk_id": f"c{i}"} for i in range(5)])

    stage = trace.stages[0]
    assert [candidate["chunk_id"] for candidate in stage["candidates"]] == ["c0", "c1"]
    assert stage["candidates_truncated"] is True
    assert stage["kept_count"] == 5
    assert trace.to_payload()["truncated"] is True


def test_stages_beyond_the_bound_are_dropped_and_flagged():
    trace = RetrievalTrace(max_stages=1)
    trace.record_stage(STAGE_BASE, [{"chunk_id": "c1"}])
    trace.record_stage(STAGE_PASS_TWO, [{"chunk_id": "c2"}])

    assert [stage["stage"] for stage in trace.stages] == [STAGE_BASE]
    assert trace.truncated is True


def test_final_context_displaces_diagnostic_stage_when_bound_is_full():
    trace = RetrievalTrace(max_stages=2)
    trace.record_stage(STAGE_BASE, [{"chunk_id": "base"}])
    trace.record_stage(STAGE_PASS_ONE, [{"chunk_id": "pass-one"}])
    trace.record_stage(STAGE_FINAL_CONTEXT, [{"chunk_id": "final"}])

    assert len(trace.stages) == 2
    assert trace.final_context_stage() is trace.stages[-1]
    assert trace.stages[-1]["candidates"][0]["chunk_id"] == "final"
    assert trace.truncated is True


def test_empty_final_context_is_still_explicit_when_bound_is_full():
    trace = RetrievalTrace(max_stages=1)
    trace.record_stage(STAGE_BASE, [{"chunk_id": "base"}])
    trace.record_stage(STAGE_FINAL_CONTEXT, [])

    assert trace.stages == [trace.final_context_stage()]
    assert trace.stages[0]["kept_count"] == 0
    assert trace.stages[0]["candidates"] == []
    assert trace.truncated is True


def test_a_long_query_is_truncated():
    trace = RetrievalTrace(max_query_chars=10)
    trace.record_stage(STAGE_BASE, [], query="q" * 40)

    assert trace.stages[0]["query"] == "q" * 10 + "..."
    assert trace.truncated is True


def test_a_decision_keeps_only_scalar_detail():
    """A branch's inputs are thresholds and scores, never objects."""
    trace = RetrievalTrace()
    trace.record_decision(
        STAGE_PASS_TWO,
        "skipped",
        reason="sufficient_pass_one",
        detail={"top_score": 0.8, "chunks": [{"text": "private"}]},
    )

    assert trace.decisions[0]["detail"] == {"top_score": 0.8}


def test_provenance_is_empty_without_a_final_context():
    """Nothing was selected yet, so there is nothing to explain."""
    trace = RetrievalTrace()
    trace.record_stage(STAGE_PASS_ONE, [{"chunk_id": "c1"}])

    assert trace.to_payload()["provenance"] == []


def test_provenance_reports_where_a_chunk_entered_and_how_it_moved():
    trace = RetrievalTrace()
    trace.record_stage(STAGE_PASS_ONE, [{"chunk_id": "c1"}, {"chunk_id": "c2"}])
    trace.record_stage(STAGE_PASS_TWO, [{"chunk_id": "c3"}])
    trace.record_stage(STAGE_MERGED, [{"chunk_id": "c3"}, {"chunk_id": "c1"}])
    trace.record_stage(STAGE_FINAL_CONTEXT, [{"chunk_id": "c3"}, {"chunk_id": "c1"}])

    provenance = {row["chunk_id"]: row for row in trace.to_payload()["provenance"]}

    assert provenance["c3"]["first_seen_stage"] == STAGE_PASS_TWO
    assert provenance["c3"]["final_rank"] == 1
    assert provenance["c3"]["ranks_by_stage"] == {STAGE_PASS_TWO: 1, STAGE_MERGED: 1}
    # c1 led pass one and was demoted by the merge: the movement an aggregate
    # score cannot show.
    assert provenance["c1"]["first_seen_stage"] == STAGE_PASS_ONE
    assert provenance["c1"]["ranks_by_stage"] == {STAGE_PASS_ONE: 1, STAGE_MERGED: 2}


# ── The eligibility gate's refusals ───────────────────────────────────────

def test_partition_reports_why_each_refused_candidate_was_refused():
    """'Never retrieved' and 'retrieved then barred' are opposite bugs."""
    eligible, dropped = partition_eligible(
        {
            "chunks": [
                {"chunk_id": "c1"},
                {"chunk_id": "c2", "retrieval_allowed": False},
                {"chunk_id": "c3", "review_status": "removed"},
            ]
        }
    )

    assert [chunk["chunk_id"] for chunk in eligible] == ["c1"]
    assert dropped == [
        {"chunk_id": "c2", "reason": DROP_RETRIEVAL_NOT_ALLOWED},
        {"chunk_id": "c3", "reason": DROP_REVIEW_REMOVED},
    ]


# ── Bound to a retrieval eval item ────────────────────────────────────────

BARRED_RESPONSES = {
    "first": {
        "chunks": [
            {"chunk_id": "c1", "score": 0.9, "file_id": "f1"},
            # The item's own golden chunk, retrieved and then refused. Its
            # Recall@10 is 0 either way; only the trace says which.
            {"chunk_id": "c9", "score": 0.7, "review_status": "removed"},
        ]
    },
}


def test_a_retrieval_item_row_carries_its_candidate_lineage():
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}],
        backend=FakeBackend(BARRED_RESPONSES),
    )

    run = execute(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]
    payload = row["retrieval_trace"]
    stages = stages_by_name(payload)

    base = stages[STAGE_BASE]
    assert base["query"] == "first"
    assert base["requested_k"] == 20
    assert base["returned_count"] == 2
    assert base["kept_count"] == 1
    assert base["candidates"] == [
        {"rank": 1, "chunk_id": "c1", "file_id": "f1", "score": 0.9}
    ]
    assert base["dropped"] == [{"chunk_id": "c9", "reason": DROP_REVIEW_REMOVED}]
    # The context the item was scored over, and where it came from.
    assert stages[STAGE_FINAL_CONTEXT]["candidates"][0]["chunk_id"] == "c1"
    assert payload["provenance"][0]["first_seen_stage"] == STAGE_BASE


def test_a_failed_item_keeps_the_lineage_it_reached():
    """The step an item died on is the most useful thing it can report."""
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}],
        backend=FakeBackend(BARRED_RESPONSES, fail_queries={"first"}),
    )

    run = execute(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]

    assert row["error"]
    assert row["retrieval_trace"]["stages"] == []


def test_an_unscorable_item_is_not_given_a_trace_of_a_search_it_never_ran():
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["gone"]}],
        backend=FakeBackend(BARRED_RESPONSES, index=set()),
        eval_stale_label_policy="mark_unscorable",
    )

    run = execute(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]

    assert row["unscorable"] is True
    assert "retrieval_trace" not in row


# ── Bound to a full conversation turn ─────────────────────────────────────

def run_turn(
    question: str,
    mode: str,
    trace: RetrievalTrace | None = None,
    **config_overrides: Any,
):
    service, _, _ = build_service()
    for key, value in config_overrides.items():
        setattr(service.graph_runner.config, key, value)
    with bound_context(**TEST_IDENTITY.to_dict()):
        request = service.build_request({"question": question, "mode": mode})
        emitter = CollectingConversationEmitter(request)
        return asyncio.run(
            service.graph_runner.run(request, emitter, retrieval_trace=trace)
        )


def test_a_user_turn_without_a_collector_carries_no_trace():
    """The payload a normal turn returns is unchanged by this feature."""
    result = run_turn("What is RAG?", "regular")

    assert "retrieval_trace" not in result


def test_an_extended_turn_trace_explains_candidate_movement_end_to_end():
    trace = RetrievalTrace()

    # This question makes the rewriter emit a pass-two hint, so the turn runs
    # both passes — the case an aggregate score explains worst.
    result = run_turn("Please do a second retrieval", "extended", trace)

    payload = trace.to_payload()
    stages = stages_by_name(payload)
    assert set(stages) >= {STAGE_PASS_ONE, STAGE_MERGED, STAGE_PASS_TWO, STAGE_FINAL_CONTEXT}
    assert stages[STAGE_PASS_ONE]["query_source"] == "rewritten_query"
    assert stages[STAGE_PASS_ONE]["candidates"][0]["chunk_id"] == "c1"

    decisions = {decision["stage"]: decision for decision in payload["decisions"]}
    assert decisions[STAGE_PASS_TWO]["decision"] == "triggered"
    assert decisions[STAGE_PASS_TWO]["reason"] == "pass_two_hint"
    assert decisions[STAGE_PASS_TWO]["detail"]["score_threshold"] == 0.5

    # The second pass's chunk is in the answer's context, and the trace says
    # it arrived there rather than having been a pass-one candidate.
    provenance = {row["chunk_id"]: row for row in payload["provenance"]}
    assert provenance["c2"]["first_seen_stage"] == STAGE_PASS_TWO
    assert [chunk["chunk_id"] for chunk in result["sources"]] == list(provenance)


def test_a_skipped_second_pass_is_recorded_as_a_decision():
    """An absent stage must not be mistaken for an absent measurement."""
    trace = RetrievalTrace()

    # Thresholds this turn's single pass-one chunk clears, which is what
    # makes the second pass unnecessary rather than merely absent.
    run_turn(
        "What is RAG?",
        "extended",
        trace,
        pass_two_chunk_threshold=1,
        pass_two_score_threshold=0.1,
    )

    decisions = {decision["stage"]: decision for decision in trace.decisions}
    assert decisions[STAGE_PASS_TWO]["decision"] == "skipped"
    assert decisions[STAGE_PASS_TWO]["reason"] == "sufficient_pass_one"
    assert STAGE_PASS_TWO not in stages_by_name(trace.to_payload())


def test_a_revised_turn_records_one_terminal_context_not_two():
    """Two terminal stages would leave a reader with two answers to one question."""
    trace = RetrievalTrace()

    run_turn("Please do a second retrieval", "extended", trace)

    names = [stage["stage"] for stage in trace.stages]
    assert names.count(STAGE_FINAL_CONTEXT) == 1


def test_the_terminal_context_survives_a_full_bound_and_a_later_failure():
    """Neither the stage bound nor a downstream failure may erase it."""
    service, backend, _ = build_service()
    backend.fail_generation = True
    trace = RetrievalTrace(max_stages=1)

    with bound_context(**TEST_IDENTITY.to_dict()):
        request = service.build_request({"question": "Break generation", "mode": "regular"})
        emitter = CollectingConversationEmitter(request)
        result = asyncio.run(
            service.graph_runner.run(request, emitter, retrieval_trace=trace)
        )

    assert result["outcome"] == "failed"
    final = trace.final_context_stage()
    assert final is not None
    assert [candidate["chunk_id"] for candidate in final["candidates"]] == ["c1"]
    assert trace.to_payload()["truncated"] is True


def test_an_end_to_end_eval_item_is_traced_by_the_graph_itself():
    store, runner, _, dataset_id = build(
        items=[{"query": "What is RAG?", "relevant_chunk_ids": ["c1"]}],
    )
    service, _, _ = build_service()
    runner.graph_runner = service.graph_runner

    async def _go():
        run = await runner.start_run(dataset_id, MODE_END_TO_END)
        await asyncio.gather(*list(runner._tasks))
        return run

    with bound_context(**ADMIN.to_dict()):
        run = asyncio.run(_go())
    row = fetch(store, run["run_id"])["per_item"][0]

    stages = stages_by_name(row["retrieval_trace"])
    assert STAGE_FINAL_CONTEXT in stages
    assert stages[STAGE_FINAL_CONTEXT]["candidates"][0]["chunk_id"] == "c1"
    assert row["retrieved_ids"][0] == "c1"
    assert row["first_hit_rank"] == 1
    assert row["reciprocal_rank"] == 1.0
