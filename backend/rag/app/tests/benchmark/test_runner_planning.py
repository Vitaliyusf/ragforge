"""Profile semantics and phase planning: cost order, supported phases, refusals."""
from __future__ import annotations

import asyncio

import pytest

from app.services.benchmark_runner import (
    BENCHMARK_PROFILES,
    PHASE_END_TO_END_EXTENDED,
    PHASE_END_TO_END_REGULAR,
    PHASE_NAMES,
    PHASE_QUEUED,
    PHASE_RETRIEVAL_BASE,
    PHASE_RETRIEVAL_EXTENDED,
    PHASE_UNSUPPORTED,
    PROFILE_EXTENDED_COMPARISON,
    PROFILE_FULL_DIAGNOSTIC,
    PROFILE_FULL_QUALITY,
    PROFILE_QUICK_RETRIEVAL,
    PROFILE_SMOKE_QUALITY,
    phases_for_profile,
    plan_phases,
)
from app.services.eval_runner import (
    MODE_END_TO_END,
    MODE_RETRIEVAL,
    PIPELINE_EXTENDED,
    PIPELINE_REGULAR,
)
from app.services.eval_store import (
    EvalValidationError,
    canonical_items,
    dataset_fingerprint,
)

from shared.context import bound_context

from app.tests.benchmark._harness import (
    ADMIN,
    FakeGraphRunner,
    build,
    fetch,
    phases_by_name,
    run_benchmark,
)

def test_phases_run_cheapest_first():
    """A free phase that fails must report before an expensive one spends."""
    plan = plan_phases(None, graph_available=True)

    assert [phase["name"] for phase in plan] == list(PHASE_NAMES)
    assert plan[0]["name"] == PHASE_RETRIEVAL_BASE
    assert plan[0]["evaluation_mode"] == MODE_RETRIEVAL


def test_each_profile_maps_to_its_explicit_phase_selection():
    assert BENCHMARK_PROFILES == {
        PROFILE_QUICK_RETRIEVAL: (PHASE_RETRIEVAL_BASE,),
        PROFILE_SMOKE_QUALITY: (PHASE_END_TO_END_REGULAR,),
        PROFILE_FULL_QUALITY: (PHASE_RETRIEVAL_BASE, PHASE_END_TO_END_REGULAR),
        PROFILE_EXTENDED_COMPARISON: (
            PHASE_END_TO_END_REGULAR,
            PHASE_END_TO_END_EXTENDED,
        ),
        PROFILE_FULL_DIAGNOSTIC: (
            PHASE_RETRIEVAL_BASE,
            PHASE_RETRIEVAL_EXTENDED,
            PHASE_END_TO_END_REGULAR,
            PHASE_END_TO_END_EXTENDED,
        ),
    }
    assert PHASE_END_TO_END_EXTENDED not in phases_for_profile(PROFILE_FULL_QUALITY)
    diagnostic = plan_phases(
        phases_for_profile(PROFILE_FULL_DIAGNOSTIC), graph_available=True
    )
    assert phases_by_name({"phases": diagnostic})[PHASE_RETRIEVAL_EXTENDED][
        "status"
    ] == PHASE_UNSUPPORTED


def test_unknown_profile_is_refused():
    with pytest.raises(EvalValidationError, match="Unknown benchmark profile"):
        phases_for_profile("quality_plus_magic")


def test_the_requested_order_does_not_override_the_cost_order():
    plan = plan_phases(
        [PHASE_END_TO_END_REGULAR, PHASE_RETRIEVAL_BASE], graph_available=True
    )

    assert [phase["name"] for phase in plan] == [
        PHASE_RETRIEVAL_BASE,
        PHASE_END_TO_END_REGULAR,
    ]


def test_extended_retrieval_is_unsupported_rather_than_faked():
    """It would report the base numbers under an extended label."""
    plan = phases_by_name({"phases": plan_phases(None, graph_available=True)})

    assert plan[PHASE_RETRIEVAL_EXTENDED]["status"] == PHASE_UNSUPPORTED
    assert "end_to_end_extended" in plan[PHASE_RETRIEVAL_EXTENDED]["reason"]


def test_answer_phases_are_unsupported_without_a_graph():
    """Blank answer-quality columns would look like a measured zero."""
    plan = phases_by_name({"phases": plan_phases(None, graph_available=False)})

    assert plan[PHASE_END_TO_END_REGULAR]["status"] == PHASE_UNSUPPORTED
    assert plan[PHASE_END_TO_END_EXTENDED]["status"] == PHASE_UNSUPPORTED
    assert plan[PHASE_RETRIEVAL_BASE]["status"] == PHASE_QUEUED


def test_a_selection_nothing_can_run_is_refused():
    with pytest.raises(EvalValidationError):
        plan_phases([PHASE_END_TO_END_REGULAR], graph_available=False)


def test_an_unknown_phase_is_refused():
    with pytest.raises(EvalValidationError):
        plan_phases(["retrieval_turbo"], graph_available=True)


# ── Evaluation mode is not pipeline mode ──────────────────────────────────


def test_each_phase_records_both_modes_separately():
    """A phase is a point in the grid, not a value in one enumeration."""
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)

    assert plan[PHASE_RETRIEVAL_BASE]["evaluation_mode"] == MODE_RETRIEVAL
    # A retrieval phase drives no pipeline, and says so rather than claiming
    # the default one.
    assert plan[PHASE_RETRIEVAL_BASE]["pipeline_mode"] is None
    assert plan[PHASE_END_TO_END_REGULAR]["evaluation_mode"] == MODE_END_TO_END
    assert plan[PHASE_END_TO_END_REGULAR]["pipeline_mode"] == PIPELINE_REGULAR
    assert plan[PHASE_END_TO_END_EXTENDED]["evaluation_mode"] == MODE_END_TO_END
    assert plan[PHASE_END_TO_END_EXTENDED]["pipeline_mode"] == PIPELINE_EXTENDED


def test_the_pipeline_mode_reaches_the_graph():
    """The extended phase must actually drive the extended pipeline."""
    graph = FakeGraphRunner()
    store, orchestrator, _, dataset_id = build(graph=graph)

    run_benchmark(orchestrator, dataset_id)

    assert {call["pipeline_mode"] for call in graph.calls} == {
        PIPELINE_REGULAR,
        PIPELINE_EXTENDED,
    }


def test_each_phase_run_carries_both_modes_and_its_benchmark():
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)
    with bound_context(**ADMIN.to_dict()):
        run = store.get_run(plan[PHASE_END_TO_END_EXTENDED]["run_id"])

    assert run["mode"] == MODE_END_TO_END
    assert run["pipeline_mode"] == PIPELINE_EXTENDED
    assert run["config_snapshot"]["pipeline_mode"] == PIPELINE_EXTENDED
    assert run["benchmark_id"] == benchmark["benchmark_id"]


# ── Progress ──────────────────────────────────────────────────────────────


def test_a_benchmark_captures_only_its_immutable_canonical_scoring_snapshot():
    store, orchestrator, _, dataset_id = build(
        items=[
            {
                "item_id": "authoring-id",
                "query": "first",
                "relevant_chunk_ids": ["c1"],
                "notes": "private annotation",
                "created_by": "admin-a",
            }
        ]
    )

    benchmark = fetch(
        store,
        run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])["benchmark_id"],
    )
    snapshot = benchmark["dataset_snapshot"]

    assert snapshot["dataset_id"] == dataset_id
    assert snapshot["dataset_version"] == benchmark["dataset_version"]
    assert snapshot["dataset_sha256"] == benchmark["dataset_sha256"]
    assert dataset_fingerprint(snapshot["items"]) == snapshot["dataset_sha256"]
    # The snapshot is the canonical scoring form of the stored dataset — the
    # items as they were normalized at import, which is what the run scored.
    with bound_context(**ADMIN.to_dict()):
        stored = store.get_dataset(dataset_id)["items"]
    assert canonical_items(snapshot["items"]) == canonical_items(stored)
    # The phase executes this snapshot, so item identity has to survive it;
    # the fingerprint assertion above proves it stays outside the hash.
    assert snapshot["items"][0]["item_id"] == stored[0]["item_id"]
    assert "notes" not in snapshot["items"][0]
    assert "created_by" not in snapshot["items"][0]


def test_benchmark_phase_rows_keep_the_item_identity_they_were_scored_under():
    """The snapshot a phase executes must not erase per-item identity.

    Rows are the only per-item evidence a drill-down or export has, and an
    ``item_id`` shared by every row cannot be joined back to a golden set
    item. The unscorable lookup is keyed by the same field, so one blank id
    would also let a single stale label mark the whole phase unscorable.
    """
    store, orchestrator, _, dataset_id = build()

    benchmark = fetch(
        store,
        run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])["benchmark_id"],
    )
    with bound_context(**ADMIN.to_dict()):
        dataset_ids = {item["item_id"] for item in store.get_dataset(dataset_id)["items"]}
        run = store.get_run(str(benchmark["phases"][0]["run_id"]))

    scored_ids = [row.get("item_id") for row in run["per_item"]]
    assert len(set(scored_ids)) == len(scored_ids)
    assert set(scored_ids) == dataset_ids



def test_profile_persists_and_manifest_records_the_execution_plan():
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    async def _go():
        benchmark = await orchestrator.start_benchmark(
            dataset_id, profile=PROFILE_FULL_QUALITY
        )
        await asyncio.gather(*list(orchestrator._tasks))
        return benchmark

    with bound_context(**ADMIN.to_dict()):
        benchmark = asyncio.run(_go())
    stored = fetch(store, benchmark["benchmark_id"])

    assert stored["profile"] == PROFILE_FULL_QUALITY
    assert stored["manifest"]["execution"] == {
        "requested_profile": PROFILE_FULL_QUALITY,
        "executable_phases": [PHASE_RETRIEVAL_BASE, PHASE_END_TO_END_REGULAR],
        "unsupported_phases": [],
        "skipped_phases": [PHASE_RETRIEVAL_EXTENDED, PHASE_END_TO_END_EXTENDED],
    }


def test_omitted_profile_defaults_to_full_quality():
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    async def _go():
        benchmark = await orchestrator.start_benchmark(dataset_id)
        await asyncio.gather(*list(orchestrator._tasks))
        return benchmark

    with bound_context(**ADMIN.to_dict()):
        benchmark = asyncio.run(_go())

    assert benchmark["profile"] == PROFILE_FULL_QUALITY
    assert [phase["name"] for phase in benchmark["phases"]] == [
        PHASE_RETRIEVAL_BASE,
        PHASE_END_TO_END_REGULAR,
    ]



def test_the_manifest_is_written_once_at_plan_time():
    """Config drifting mid-benchmark must not rewrite what the phases ran on."""
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    captured = benchmark["manifest"]["captured_at"]
    orchestrator.config.top_k_documents = 99

    stored = fetch(store, benchmark["benchmark_id"])["manifest"]
    assert stored["captured_at"] == captured
    assert stored["retrieval"]["top_k_documents"] == 6


