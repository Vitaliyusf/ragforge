"""End-to-end pipeline runs: mode selection, answer quality, and failure accounting."""
from __future__ import annotations

import asyncio

import pytest

from app.services.eval_runner import (
    MODE_END_TO_END,
    MODE_RETRIEVAL,
    PIPELINE_EXTENDED,
    PIPELINE_REGULAR,
    aggregate,
)
from app.services.eval_store import EvalValidationError
from shared.context import bound_context

from app.tests.eval._harness import (
    ADMIN,
    GRAPH_RESULTS,
    FailingGraph,
    FakeGraphRunner,
    build,
    execute,
    fetch,
    run_end_to_end,
)

def test_retrieval_stays_the_default_mode():
    """The free run is what a caller gets by saying nothing."""
    store, runner, backend, dataset_id = build()

    run = execute(runner, dataset_id)

    assert fetch(store, run["run_id"])["mode"] == MODE_RETRIEVAL
    assert fetch(store, run["run_id"])["config_snapshot"]["mode"] == MODE_RETRIEVAL


def test_default_run_never_touches_the_graph():
    """The phase-5 promise: a retrieval run costs nothing."""
    store, runner, backend, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    execute(runner, dataset_id)

    assert runner.graph_runner.calls == []


def test_end_to_end_mode_is_refused_without_a_graph():
    """Better a refusal than a run whose answer columns are silently blank."""
    store, runner, _, dataset_id = build()

    async def _go():
        with pytest.raises(EvalValidationError):
            await runner.start_run(dataset_id, MODE_END_TO_END)

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_an_unknown_mode_is_refused():
    store, runner, _, dataset_id = build()

    async def _go():
        with pytest.raises(EvalValidationError):
            await runner.start_run(dataset_id, "cheap")

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_a_retrieval_run_records_no_pipeline_it_did_not_drive():
    """Its one search is not routed through a conversation pipeline."""
    store, runner, _, dataset_id = build()

    run = fetch(store, execute(runner, dataset_id)["run_id"])

    assert run["pipeline_mode"] is None
    assert run["config_snapshot"]["pipeline_mode"] is None


def test_a_pipeline_mode_on_a_retrieval_run_is_refused_not_ignored():
    """Accepting it would let identical runs record different pipelines."""
    store, runner, _, dataset_id = build()

    async def _go():
        with pytest.raises(EvalValidationError):
            await runner.start_run(dataset_id, MODE_RETRIEVAL, PIPELINE_EXTENDED)

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_an_unknown_pipeline_mode_is_refused():
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    async def _go():
        with pytest.raises(EvalValidationError):
            await runner.start_run(dataset_id, MODE_END_TO_END, "turbo")

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_an_end_to_end_run_defaults_to_the_regular_pipeline():
    """Saying nothing must not leave the axis unrecorded."""
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    run = fetch(store, run_end_to_end(runner, dataset_id)["run_id"])

    assert run["pipeline_mode"] == PIPELINE_REGULAR


def test_an_extended_run_drives_the_extended_pipeline():
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    async def _go():
        run = await runner.start_run(dataset_id, MODE_END_TO_END, PIPELINE_EXTENDED)
        await asyncio.gather(*list(runner._tasks))
        return run

    with bound_context(**ADMIN.to_dict()):
        run = asyncio.run(_go())

    assert fetch(store, run["run_id"])["pipeline_mode"] == PIPELINE_EXTENDED
    assert {call["pipeline_mode"] for call in runner.graph_runner.calls} == {
        PIPELINE_EXTENDED
    }


def test_end_to_end_run_reports_answer_quality_and_retrieval():
    """Both halves are scored: the run replaces neither measure."""
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    run = run_end_to_end(runner, dataset_id)
    results = fetch(store, run["run_id"])["results"]
    quality = results["answer_quality"]

    assert results["mrr"] == pytest.approx((1.0 + 1.0) / 2)
    assert quality["groundedness"]["mean"] == pytest.approx(0.7)
    # One of the two items cited nothing, so precision is a mean of one.
    assert quality["citation_precision"] == {"mean": 1.0, "counted": 1, "excluded": 1}
    assert quality["citation_recall"]["mean"] == pytest.approx(0.5)
    assert quality["hallucination_rate"] == pytest.approx(0.5)
    assert quality["hallucination_severe_rate"] == pytest.approx(0.5)
    assert quality["items_judged"] == 2


def test_end_to_end_scoring_uses_reordered_final_context_not_base_stage():
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}]
    )

    class ReorderedGraph(FakeGraphRunner):
        async def run(self, request, emitter, **kwargs):
            trace = kwargs["retrieval_trace"]
            trace.record_stage(
                "base", [{"chunk_id": "c1"}, {"chunk_id": "c2"}]
            )
            return await super().run(request, emitter, **kwargs)

    runner.graph_runner = ReorderedGraph(
        {"first": {"sources": [{"chunk_id": "c2"}, {"chunk_id": "c1"}]}}
    )

    run = run_end_to_end(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]

    assert row["retrieved_ids"] == ["c2", "c1"]
    assert row["first_hit_rank"] == 2
    assert row["reciprocal_rank"] == 0.5


def test_end_to_end_allows_explicitly_empty_final_context():
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}]
    )

    class EmptyFinalGraph(FakeGraphRunner):
        async def run(self, request, emitter, **kwargs):
            kwargs["retrieval_trace"].record_stage("base", [{"chunk_id": "c1"}])
            return await super().run(request, emitter, **kwargs)

    runner.graph_runner = EmptyFinalGraph({"first": {"sources": []}})

    run = run_end_to_end(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]

    assert row["outcome"] == "success"
    assert row["retrieved_ids"] == []
    assert row["reciprocal_rank"] == 0.0
    final = row["retrieval_trace"]["stages"][-1]
    assert final["stage"] == "final_context"
    assert final["kept_count"] == 0


def test_success_without_final_context_is_failed_not_scored_as_a_miss():
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}]
    )

    class MissingEvidenceGraph(FakeGraphRunner):
        async def run(self, request, emitter, **kwargs):
            kwargs["retrieval_trace"].record_stage("base", [{"chunk_id": "c1"}])
            return {"outcome": "success", "sources": []}

    runner.graph_runner = MissingEvidenceGraph({})

    run = run_end_to_end(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    row = stored["per_item"][0]

    assert row["outcome"] == "failed"
    assert row["error_class"] == "EvalEvidenceConsistencyError"
    assert "final-context evidence" in row["error"]
    assert "scores" not in row
    assert stored["results"]["items_evaluated"] == 0



def test_a_post_retrieval_failure_keeps_its_error_and_still_scores_retrieval():
    """The generator failing is not the retriever missing."""
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}]
    )
    runner.graph_runner = FailingGraph(
        {
            "outcome": "failed",
            "error": "structured output validation failed",
            "error_class": "ValueError",
            "failed_node": "evaluate_answer_light",
            "answer": "",
            "sources": [{"chunk_id": "c1"}],
        },
        context=[{"chunk_id": "c1"}],
    )

    run = run_end_to_end(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    row = stored["per_item"][0]

    # The primary pipeline failure, not the secondary evidence complaint.
    assert row["outcome"] == "failed"
    assert row["error"] == "structured output validation failed"
    assert row["error_class"] == "ValueError"
    assert row["failed_node"] == "evaluate_answer_light"
    # Retrieval was measured and is scored on its own axis.
    assert row["retrieved_ids"] == ["c1"]
    assert row["first_hit_rank"] == 1
    assert row["reciprocal_rank"] == 1.0
    assert row["retrieval_trace"]["stages"][-1]["stage"] == "final_context"
    # Answer quality was never measured, so it contributes nothing.
    assert row.get("groundedness") is None
    assert stored["results"]["items_evaluated"] == 1
    assert stored["results"]["execution"]["failed"] == 1
    assert stored["results"]["scoring"]["scored"] == 1
    assert stored["results"]["answer_quality"]["items_judged"] == 0


def test_a_pre_retrieval_failure_fabricates_no_retrieval_evidence():
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}]
    )
    runner.graph_runner = FailingGraph(
        {
            "outcome": "failed",
            "error": "vector store unavailable",
            "error_class": "RuntimeError",
            "failed_node": "retrieve_chunks_once",
            "answer": "",
            "sources": [],
        }
    )

    run = run_end_to_end(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    row = stored["per_item"][0]

    assert row["outcome"] == "failed"
    assert row["error"] == "vector store unavailable"
    assert row["failed_node"] == "retrieve_chunks_once"
    assert row["retrieved_ids"] == []
    # Unmeasured, not missed: a zero here would be a regression nobody caused.
    assert "scores" not in row
    assert row["reciprocal_rank"] is None
    assert stored["results"]["items_evaluated"] == 0
    assert stored["results"]["scoring"]["unscorable"] == 1


def test_a_graph_error_without_an_outcome_is_still_a_failure_not_a_success():
    """The pre-contract result shape must not default to success."""
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}]
    )
    runner.graph_runner = FailingGraph({"error": "boom", "answer": "", "sources": []})

    run = run_end_to_end(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]

    assert row["outcome"] == "failed"
    assert row["error"] == "boom"
    assert row["error_class"] == "ConversationGraphError"


def test_a_primary_graph_error_outranks_an_evidence_inconsistency():
    """A failed graph already said what went wrong; that must reach the row."""
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}]
    )
    # Sources without a terminal stage: incoherent evidence *and* a real
    # failure. The failure is the one worth reporting.
    runner.graph_runner = FailingGraph(
        {
            "outcome": "failed",
            "error": "generation failed",
            "error_class": "RuntimeError",
            "failed_node": "generate_answer",
            "sources": [{"chunk_id": "c1"}],
        }
    )

    run = run_end_to_end(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]

    assert row["error"] == "generation failed"
    assert row["error_class"] == "RuntimeError"
    assert "scores" not in row


def test_mixed_outcomes_are_accounted_on_independent_axes():
    """Execution, retrieval scoring and answer quality each count separately."""
    store, runner, _, dataset_id = build(
        items=[
            {"query": "first", "relevant_chunk_ids": ["c1"]},
            {"query": "second", "relevant_chunk_ids": ["c1"]},
            {"query": "third", "relevant_chunk_ids": ["c9"]},
            {"query": "fourth", "relevant_chunk_ids": ["c1"]},
        ]
    )

    class MixedGraph(FakeGraphRunner):
        async def run(self, request, emitter, **kwargs):
            trace = kwargs["retrieval_trace"]
            query = request.user_message
            await asyncio.sleep(0)
            if query == "first":
                trace.record_stage("final_context", [{"chunk_id": "c1"}])
                return {
                    "answer": "Alpha [1].",
                    "sources": [{"chunk_id": "c1"}],
                    "review": {
                        "groundedness_score": 0.8,
                        "hallucination_verdict": "none",
                    },
                }
            if query == "second":
                # Post-retrieval failure: the context is known, the judge died.
                trace.record_stage("final_context", [{"chunk_id": "c1"}])
                return {
                    "outcome": "failed",
                    "error": "judge timed out",
                    "error_class": "TimeoutError",
                    "failed_node": "evaluate_answer_light",
                    "sources": [{"chunk_id": "c1"}],
                }
            if query == "third":
                # Pre-retrieval failure: no context ever existed.
                return {
                    "outcome": "failed",
                    "error": "vector store unavailable",
                    "error_class": "RuntimeError",
                    "failed_node": "retrieve_chunks_once",
                    "sources": [],
                }
            return {
                "outcome": "guardrail_blocked",
                "guardrail_stage": "input",
                "sources": [],
            }

    runner.graph_runner = MixedGraph({})

    stored = fetch(store, run_end_to_end(runner, dataset_id)["run_id"])
    results = stored["results"]

    assert results["execution"] == {
        "total": 4,
        "succeeded": 1,
        "guardrail_blocked": 1,
        "failed": 2,
        "timed_out": 0,
        "interrupted": 0,
    }
    # The post-retrieval failure is scored for retrieval; the pre-retrieval
    # failure and the guardrail block are not.
    assert results["scoring"] == {
        "dataset_items": 4,
        "scored": 2,
        "skipped": 0,
        "unscorable": 2,
    }
    assert results["mrr"] == pytest.approx(1.0)
    assert results["answer_quality"]["items_judged"] == 1
    assert results["items_guardrail_blocked"] == 1
    assert results["items_failed"] == 2


def test_guardrail_blocked_items_are_separate_from_failures_and_answer_denominators():
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner({
        **GRAPH_RESULTS,
        "first": {"outcome": "guardrail_blocked", "guardrail_stage": "input", "sources": []},
    })

    run = run_end_to_end(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    blocked = next(row for row in stored["per_item"] if row["query"] == "first")

    assert blocked["outcome"] == "guardrail_blocked"
    assert blocked["guardrail_stage"] == "input"
    assert blocked["error"] is None
    assert stored["results"]["items_guardrail_blocked"] == 1
    assert stored["results"]["items_failed"] == 0
    assert stored["results"]["execution"] == {
        "total": 2,
        "succeeded": 1,
        "guardrail_blocked": 1,
        "failed": 0,
        "timed_out": 0,
        "interrupted": 0,
    }
    assert stored["results"]["scoring"] == {
        "dataset_items": 2,
        "scored": 1,
        "skipped": 0,
        "unscorable": 1,
    }
    assert stored["results"]["answer_quality"]["items_unjudged"] == 0


def test_end_to_end_turns_are_kept_out_of_the_live_turn_facts():
    """Synthetic turns must not move the averages the run is measuring."""
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    run_end_to_end(runner, dataset_id)

    assert runner.graph_runner.calls
    assert all(call["record_metrics"] is False for call in runner.graph_runner.calls)


def test_end_to_end_mode_is_recorded_in_the_config_snapshot():
    """So the config-diff warning fires when the two modes are compared."""
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    run = run_end_to_end(runner, dataset_id)
    stored = fetch(store, run["run_id"])

    assert stored["mode"] == MODE_END_TO_END
    assert stored["config_snapshot"]["mode"] == MODE_END_TO_END
    # Scored over the graph's own sources, so the depth recorded is the
    # production one — claiming the eval depth would name a candidate pool
    # this run never saw.
    assert stored["config_snapshot"]["candidate_k"] == 6
    # This mode does drive the graph, so the stages it reaches are recorded
    # with their real settings rather than as null.
    assert stored["config_snapshot"]["context_k"] == 6
    assert stored["config_snapshot"]["reranker_implementation"] == "score_order_merge"
    assert stored["config_snapshot"]["pass_two_active"] is True


def test_end_to_end_respects_the_phase_five_concurrency_bound():
    """The heavier mode gets the same bound, not a larger one."""
    store, runner, _, dataset_id = build(
        items=[{"query": f"q{i}", "relevant_chunk_ids": ["c1"]} for i in range(8)],
        eval_run_concurrency=2,
    )

    class CountingGraph(FakeGraphRunner):
        def __init__(self):
            super().__init__({})
            self.in_flight = 0
            self.max_in_flight = 0

        async def run(
            self,
            request,
            emitter,
            resume=False,
            record_metrics=True,
            retrieval_trace=None,
        ):
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            try:
                await asyncio.sleep(0)
                if retrieval_trace is not None:
                    retrieval_trace.record_stage("final_context", [])
                return {"answer": "", "sources": [], "review": {}}
            finally:
                self.in_flight -= 1

    runner.graph_runner = CountingGraph()
    run_end_to_end(runner, dataset_id)

    assert runner.graph_runner.max_in_flight <= 2


def test_an_unjudged_item_is_excluded_from_the_hallucination_rate():
    """A flaky judge must not read as an answer that did not hallucinate."""
    rows = [
        {"hallucination_verdict": "severe", "groundedness": 0.2},
        {"hallucination_verdict": None, "groundedness": None},
    ]

    quality = aggregate(rows, MODE_END_TO_END)["answer_quality"]

    assert quality["hallucination_rate"] == 1.0
    assert quality["items_judged"] == 1
    assert quality["items_unjudged"] == 1


def test_retrieval_results_carry_no_answer_quality_section():
    """A free run reports nothing it did not measure."""
    assert "answer_quality" not in aggregate([{"skipped": True}], MODE_RETRIEVAL)


# -- Stale golden-set labels ----------------------------------------------
#
# A dataset labelled against an older index can name chunks reindexing has
# since dropped. Retrieval cannot return an id that no longer exists, so
# scoring the label as a miss reports a recall regression that never
# happened. These cover the three states a label can be in and what a run
# does about each.



