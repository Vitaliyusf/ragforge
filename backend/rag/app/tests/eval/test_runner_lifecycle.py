"""Run lifecycle: state transitions, partial progress, refusal to open bad runs, concurrency and timing bounds."""
from __future__ import annotations

import asyncio

import pytest

from app.services.eval_runner import (
    EvalRunner,
)
from app.services.eval_store import EvalStore, EvalValidationError
from shared.context import bound_context

from app.tests.eval._harness import (
    ADMIN,
    ITEMS,
    FakeBackend,
    build,
    build_config,
    execute,
    fetch,
)

def test_a_run_returns_immediately_in_running_state():
    """The RPC must not block: a synchronous run would blow the timeout."""
    store, runner, _, dataset_id = build()

    async def _go():
        run = await runner.start_run(dataset_id)
        assert run["status"] == "running"
        await asyncio.gather(*list(runner._tasks))
        return run

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())



def test_partial_progress_is_persisted_as_items_complete():
    """A crashed run must leave evidence of how far it got."""
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)

    assert len(fetch(store, run["run_id"])["per_item"]) == 2



def test_a_run_whose_every_item_fails_is_marked_failed():
    backend = FakeBackend(fail_queries={"first", "third"})
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    fetched = fetch(store, run["run_id"])

    assert fetched["status"] == "failed"
    assert "embedding unavailable" in fetched["error"]
    assert fetched["finished_at"] is not None


def test_one_failing_item_does_not_discard_the_others():
    backend = FakeBackend(fail_queries={"third"})
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    fetched = fetch(store, run["run_id"])

    assert fetched["status"] == "completed"
    assert fetched["results"]["items_failed"] == 1
    assert fetched["results"]["items_evaluated"] == 1
    # The surviving item scored perfectly; the failed one is excluded, not
    # averaged in as a zero.
    assert fetched["results"]["mrr"] == pytest.approx(1.0)


def test_a_crash_inside_the_runner_still_closes_the_run():
    """`running` is indistinguishable from in-progress, so it must never
    be the resting state of a broken run."""
    store, runner, _, dataset_id = build()

    def explode(*args, **kwargs):
        raise RuntimeError("mongo write failed")

    runner.store.append_item_result = explode  # type: ignore[assignment]
    run = execute(runner, dataset_id)
    fetched = fetch(store, run["run_id"])

    assert fetched["status"] == "failed"
    assert "mongo write failed" in fetched["error"]


def test_starting_a_run_for_an_unknown_dataset_writes_no_run_document():
    store, runner, _, _ = build()

    async def _go():
        with pytest.raises(Exception):
            await runner.start_run("does-not-exist")

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())
        assert store.list_runs() == []


def test_an_empty_dataset_is_refused_before_a_run_is_opened():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    runner = EvalRunner(config, store, FakeBackend())  # type: ignore[arg-type]
    with bound_context(**ADMIN.to_dict()):
        dataset = store.create_dataset("A", None, ITEMS)
        # Bypass validation the way a corrupted document would.
        store._docs("eval_datasets")[0]["items"] = []

        async def _go():
            with pytest.raises(EvalValidationError):
                await runner.start_run(dataset["dataset_id"])

        asyncio.run(_go())
        assert store.list_runs() == []


def test_unresolved_authoring_filenames_are_refused_before_a_run_is_opened():
    store, runner, _, dataset_id = build(
        items=[{"item_id": "q1", "query": "Where?", "expected_file_names": ["guide.md"]}]
    )

    async def _go():
        with pytest.raises(EvalValidationError, match="unresolved expected_file_names"):
            await runner.start_run(dataset_id)

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())
        assert store.list_runs() == []



def test_concurrency_stays_within_the_semaphore_bound():
    """An unbounded gather over a large dataset would bury the embedding
    service, which is serving live traffic from the same instance."""
    items = [
        {"query": f"q{index}", "relevant_chunk_ids": ["c1"]} for index in range(12)
    ]
    backend = FakeBackend(responses={})
    store, runner, backend, dataset_id = build(
        items=items, backend=backend, eval_run_concurrency=3
    )
    execute(runner, dataset_id)

    assert backend.max_in_flight <= 3
    assert len(backend.calls) == 12


def test_item_timing_separates_queue_wait_from_bounded_execution():
    class DelayedBackend(FakeBackend):
        async def search_chunks(self, *args, **kwargs):
            await asyncio.sleep(0.02)
            return await super().search_chunks(*args, **kwargs)

    store, runner, _, dataset_id = build(
        items=ITEMS,
        backend=DelayedBackend(),
        eval_run_concurrency=1,
    )
    run = execute(runner, dataset_id)
    rows = fetch(store, run["run_id"])["per_item"]

    first, second = rows
    assert first["queue_wait_ms"] < first["execution_ms"]
    assert second["queue_wait_ms"] > 0
    assert second["total_elapsed_ms"] > second["execution_ms"]
    for row in rows:
        assert row["latency_ms"] == pytest.approx(row["total_elapsed_ms"])
        assert row["total_elapsed_ms"] == pytest.approx(
            row["queue_wait_ms"] + row["execution_ms"]
        )


def test_failed_item_still_records_reconciled_timing():
    store, runner, _, dataset_id = build(
        items=[{"query": "broken", "relevant_chunk_ids": ["c1"]}],
        backend=FakeBackend(fail_queries={"broken"}),
    )
    run = execute(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]

    assert row["outcome"] == "failed"
    assert row["queue_wait_ms"] >= 0
    assert row["execution_ms"] >= 0
    assert row["total_elapsed_ms"] == pytest.approx(
        row["queue_wait_ms"] + row["execution_ms"]
    )


# ── Match modes ───────────────────────────────────────────────────────────


