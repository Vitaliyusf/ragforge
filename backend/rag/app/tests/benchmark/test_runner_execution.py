"""Orchestration execution: progress, per-phase outcomes, degradation and recovery."""
from __future__ import annotations

import asyncio

import pytest

from app.services.benchmark_runner import (
    BENCHMARK_ACTIONS,
    GET_BENCHMARK_RUN,
    PHASE_COMPLETED,
    PHASE_END_TO_END_EXTENDED,
    PHASE_END_TO_END_REGULAR,
    PHASE_FAILED,
    PHASE_INTERRUPTED,
    PHASE_NAMES,
    PHASE_PARTIAL,
    PHASE_RETRIEVAL_BASE,
    PHASE_RETRIEVAL_EXTENDED,
    PHASE_SKIPPED,
    PHASE_UNSUPPORTED,
    START_BENCHMARK_RUN,
    benchmark_status,
)
from app.services.eval_store import (
    BENCHMARK_COMPLETED,
    BENCHMARK_FAILED,
    BENCHMARK_INTERRUPTED,
    BENCHMARK_PARTIAL,
    BENCHMARK_QUEUED,
    EvalNotFound,
)
from shared.auth import AuthIdentity

from shared.context import bound_context

from app.tests.benchmark._harness import (
    ADMIN,
    ITEMS,
    FakeBackend,
    FakeGraphRunner,
    build,
    fetch,
    phases_by_name,
    run_benchmark,
)

def test_a_benchmark_returns_immediately_in_queued_state():
    """A synchronous orchestration would blow the gateway timeout."""
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    async def _go():
        benchmark = await orchestrator.start_benchmark(dataset_id)
        assert benchmark["status"] == BENCHMARK_QUEUED
        assert benchmark["started_at"] is None
        await asyncio.gather(*list(orchestrator._tasks))

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_running_phase_persists_truthful_item_progress_without_poll_writes():
    blocker = asyncio.Event()
    store, orchestrator, _, dataset_id = build(backend=FakeBackend(block=blocker))

    async def _go():
        benchmark = await orchestrator.start_benchmark(dataset_id, [PHASE_RETRIEVAL_BASE])
        for _ in range(20):
            await asyncio.sleep(0)
            progress = fetch(store, benchmark["benchmark_id"])["progress"]
            if progress["current_phase"] == PHASE_RETRIEVAL_BASE:
                break
        else:
            raise AssertionError("benchmark did not enter its retrieval phase")

        before = fetch(store, benchmark["benchmark_id"])["progress"]
        again = fetch(store, benchmark["benchmark_id"])["progress"]
        assert before == again  # reads never manufacture progress
        assert before["items_completed"] == 0
        assert before["items_in_flight"] == len(ITEMS)
        assert before["phase_started_at"]
        assert before["last_progress_at"]

        blocker.set()
        await asyncio.gather(*list(orchestrator._tasks))
        return fetch(store, benchmark["benchmark_id"])

    with bound_context(**ADMIN.to_dict()):
        completed = asyncio.run(_go())

    progress = completed["progress"]
    assert progress["items_completed"] == len(ITEMS)
    assert progress["items_in_flight"] == 0
    assert progress["items_succeeded"] == len(ITEMS)
    assert (
        progress["items_succeeded"]
        + progress["items_guardrail_blocked"]
        + progress["items_failed"]
        + progress["items_timed_out"]
        == progress["items_completed"]
    )


def test_progress_counts_every_phase_and_only_the_reachable_items():
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    progress = benchmark["progress"]

    assert progress["total_phases"] == len(PHASE_NAMES)
    assert progress["executable_phases"] == 3
    assert progress["unsupported_phases"] == 1
    assert progress["completed_phases"] == 3
    assert progress["current_phase"] is None
    assert progress["items_per_phase"] == 2
    # Three executable phases over two items: the unsupported one is not a
    # denominator anybody can reach.
    assert progress["items_total"] == 6
    assert progress["items_completed"] == 6


def test_every_supported_phase_produces_its_own_run():
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)
    run_ids = [
        plan[name]["run_id"]
        for name in (
            PHASE_RETRIEVAL_BASE,
            PHASE_END_TO_END_REGULAR,
            PHASE_END_TO_END_EXTENDED,
        )
    ]

    assert benchmark["status"] == BENCHMARK_COMPLETED
    assert all(run_ids)
    assert len(set(run_ids)) == 3
    assert plan[PHASE_RETRIEVAL_EXTENDED]["run_id"] is None
    assert plan[PHASE_RETRIEVAL_BASE]["results"]["items_evaluated"] == 2



def test_a_benchmark_is_listed_and_fetched_within_its_tenant():
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    with bound_context(**ADMIN.to_dict()):
        listed = store.list_benchmark_runs(dataset_id)
    other = AuthIdentity(
        tenant_id="tenant-b", user_id="admin-b", role="admin", admin_id="admin-b"
    )

    assert [row["benchmark_id"] for row in listed] == [benchmark["benchmark_id"]]
    with bound_context(**other.to_dict()):
        assert store.list_benchmark_runs(dataset_id) == []


# ── Partial and failed ────────────────────────────────────────────────────

def test_item_failures_make_a_phase_partial_not_failed():
    """One bad query is a smaller denominator, not a lost phase."""
    backend = FakeBackend(fail_queries={"third"})
    store, orchestrator, _, dataset_id = build(backend=backend)

    benchmark = fetch(
        store,
        run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])["benchmark_id"],
    )
    phase = phases_by_name(benchmark)[PHASE_RETRIEVAL_BASE]

    assert phase["status"] == PHASE_PARTIAL
    assert phase["results"]["items_failed"] == 1
    assert phase["results"]["items_evaluated"] == 1
    assert benchmark["status"] == BENCHMARK_PARTIAL
    assert benchmark["progress"]["partial_phases"] == 1


def test_a_partial_phase_does_not_stop_the_rest():
    backend = FakeBackend(fail_queries={"third"})
    store, orchestrator, _, dataset_id = build(
        graph=FakeGraphRunner(), backend=backend
    )

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)

    assert plan[PHASE_RETRIEVAL_BASE]["status"] == PHASE_PARTIAL
    assert plan[PHASE_END_TO_END_REGULAR]["status"] == PHASE_COMPLETED
    assert plan[PHASE_END_TO_END_EXTENDED]["status"] == PHASE_COMPLETED
    assert benchmark["status"] == BENCHMARK_PARTIAL


def test_a_systemic_failure_skips_the_phases_behind_it():
    """Whatever broke the free phase breaks the expensive ones too."""
    backend = FakeBackend(fail_queries={"first", "third"})
    store, orchestrator, _, dataset_id = build(
        graph=FakeGraphRunner(), backend=backend
    )

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)

    assert plan[PHASE_RETRIEVAL_BASE]["status"] == PHASE_FAILED
    assert plan[PHASE_END_TO_END_REGULAR]["status"] == PHASE_SKIPPED
    assert plan[PHASE_END_TO_END_EXTENDED]["status"] == PHASE_SKIPPED
    assert PHASE_RETRIEVAL_BASE in plan[PHASE_END_TO_END_REGULAR]["reason"]
    # Nothing produced evidence, so the benchmark failed outright.
    assert benchmark["status"] == BENCHMARK_FAILED
    assert benchmark["error"]


def test_a_later_phase_failing_leaves_the_earlier_evidence_standing():
    store, orchestrator, _, dataset_id = build(
        graph=FakeGraphRunner(fail_queries={"first", "third"})
    )

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)

    assert plan[PHASE_RETRIEVAL_BASE]["status"] == PHASE_COMPLETED
    assert plan[PHASE_END_TO_END_REGULAR]["status"] == PHASE_FAILED
    assert plan[PHASE_END_TO_END_EXTENDED]["status"] == PHASE_SKIPPED
    assert benchmark["status"] == BENCHMARK_PARTIAL


def test_status_is_completed_only_when_nothing_was_degraded():
    completed = [
        {"status": PHASE_COMPLETED},
        {"status": PHASE_UNSUPPORTED},
    ]
    degraded = [{"status": PHASE_COMPLETED}, {"status": PHASE_FAILED}]

    assert benchmark_status(completed) == BENCHMARK_COMPLETED
    assert benchmark_status(degraded) == BENCHMARK_PARTIAL
    assert benchmark_status([{"status": PHASE_FAILED}]) == BENCHMARK_FAILED


# ── Interruption ──────────────────────────────────────────────────────────

def test_cancelling_the_orchestration_closes_it_as_interrupted():
    """A benchmark stuck in `running` is indistinguishable from a live one."""
    store, orchestrator, backend, dataset_id = build()

    async def _go():
        blocker = asyncio.Event()
        backend.block = blocker
        benchmark = await orchestrator.start_benchmark(
            dataset_id, [PHASE_RETRIEVAL_BASE]
        )
        task = next(iter(orchestrator._tasks))
        # Let the orchestration reach the blocked retrieval before cancelling.
        for _ in range(20):
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return benchmark

    with bound_context(**ADMIN.to_dict()):
        benchmark = asyncio.run(_go())

    stored = fetch(store, benchmark["benchmark_id"])

    assert stored["status"] == BENCHMARK_INTERRUPTED
    assert stored["finished_at"] is not None
    assert phases_by_name(stored)[PHASE_RETRIEVAL_BASE]["status"] == PHASE_INTERRUPTED


# ── Dispatch ──────────────────────────────────────────────────────────────


def test_the_actions_are_dispatched_and_refusals_are_typed():
    store, orchestrator, _, dataset_id = build()

    async def _go():
        started = await orchestrator.handle(
            START_BENCHMARK_RUN, {"dataset_id": dataset_id}
        )
        await asyncio.gather(*list(orchestrator._tasks))
        fetched = await orchestrator.handle(
            GET_BENCHMARK_RUN,
            {"benchmark_id": started["benchmark"]["benchmark_id"]},
        )
        missing = await orchestrator.handle(GET_BENCHMARK_RUN, {"benchmark_id": "nope"})
        return started, fetched, missing

    with bound_context(**ADMIN.to_dict()):
        started, fetched, missing = asyncio.run(_go())

    assert START_BENCHMARK_RUN in BENCHMARK_ACTIONS
    assert fetched["benchmark"]["benchmark_id"] == started["benchmark"]["benchmark_id"]
    assert missing["eval_error"]["kind"] == "not_found"


def test_a_refused_benchmark_leaves_no_document_behind():
    """The dataset is resolved before anything is written."""
    store, orchestrator, _, _ = build()

    async def _go():
        with pytest.raises(EvalNotFound):
            await orchestrator.start_benchmark("no-such-dataset")

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())
        assert store.list_benchmark_runs() == []


def test_completed_phase_persists_explicit_wall_clock_fields():
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    phase = phases_by_name(fetch(store, benchmark["benchmark_id"]))[
        PHASE_RETRIEVAL_BASE
    ]

    assert phase["phase_started_at"] == phase["started_at"]
    assert phase["phase_finished_at"] == phase["finished_at"]
    assert phase["phase_wall_clock_ms"] >= 0


# ── Manifest ──────────────────────────────────────────────────────────────


def test_a_benchmark_records_the_manifest_it_ran_under(monkeypatch):
    """Provenance is captured automatically, not remembered by an operator."""
    monkeypatch.setenv("RAGFORGE_GIT_SHA", "abc123def456")
    monkeypatch.setenv("RAGFORGE_GIT_BRANCH", "feat/benchmark-run-manifest")
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    manifest = fetch(store, benchmark["benchmark_id"])["manifest"]

    assert manifest["build"]["git_sha"] == "abc123def456"
    assert manifest["build"]["git_branch"] == "feat/benchmark-run-manifest"
    assert manifest["dataset"]["dataset_id"] == dataset_id
    assert manifest["dataset"]["item_count"] == len(ITEMS)
    assert manifest["dataset"]["phases"] == [PHASE_RETRIEVAL_BASE]
    assert manifest["retrieval"]["top_k_documents"] == 6



