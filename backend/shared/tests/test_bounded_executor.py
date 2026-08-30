import asyncio
import threading
import time
from contextvars import ContextVar

import pytest

from shared.bounded_executor import BoundedExecutor, ExecutorOverloaded
from shared.metrics import METRICS


@pytest.mark.asyncio
async def test_executor_bounds_active_and_queued_work_and_keeps_loop_responsive() -> None:
    executor = BoundedExecutor(
        service="files",
        pool="test",
        max_workers=2,
        queue_bound=1,
        submit_timeout_seconds=1.0,
    )
    release = threading.Event()
    started = threading.Event()
    active = 0
    max_active = 0
    lock = threading.Lock()

    def slow(value: int) -> int:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            started.set()
        release.wait(1.0)
        with lock:
            active -= 1
        return value

    tasks = [asyncio.create_task(executor.run(slow, value)) for value in range(6)]
    assert await asyncio.to_thread(started.wait, 0.5)
    await asyncio.sleep(0.01)
    snapshot = executor.snapshot()
    assert snapshot.active == 2
    assert snapshot.queued == 1
    assert snapshot.active + snapshot.queued <= 3
    assert not all(task.done() for task in tasks)

    release.set()
    assert await asyncio.gather(*tasks) == list(range(6))
    assert max_active == 2
    assert await executor.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service", "stage", "workers"),
    [
        ("files", "file_ingestion", 1),
        ("vector_db", "vector_search", 1),
        ("embedding", "embedding_query", 1),
        ("memory", "memory_operation", 10),
        ("llm_agent", "gateway_chat_plain", 10),
    ],
)
async def test_each_service_budget_rejects_callers_over_capacity(
    service: str,
    stage: str,
    workers: int,
) -> None:
    rejected = METRICS.executor_tasks_rejected_total.labels(
        service=service,
        pool="rpc-contract",
    )
    rejected_before = rejected._value.get()
    executor = BoundedExecutor(
        service=service,
        pool="rpc-contract",
        max_workers=workers,
        queue_bound=0,
        submit_timeout_seconds=0.02,
    )
    release = threading.Event()
    started = threading.Event()
    active = 0
    lock = threading.Lock()

    def blocked() -> None:
        nonlocal active
        with lock:
            active += 1
            if active == workers:
                started.set()
        release.wait(1.0)

    admitted = [
        asyncio.create_task(executor.run(blocked, stage=stage))
        for _ in range(workers)
    ]
    assert await asyncio.to_thread(started.wait, 0.5)
    with pytest.raises(ExecutorOverloaded) as error:
        await executor.run(lambda: None)
    assert error.value.reason == "saturated"
    assert rejected._value.get() == rejected_before + 1
    assert METRICS.executor_active_workers.labels(
        service=service,
        pool="rpc-contract",
    )._value.get() == workers
    release.set()
    await asyncio.gather(*admitted)
    assert await executor.shutdown()


@pytest.mark.asyncio
async def test_cancellation_does_not_release_running_capacity() -> None:
    executor = BoundedExecutor(
        service="memory",
        pool="test",
        max_workers=1,
        queue_bound=0,
        submit_timeout_seconds=0.02,
    )
    release = threading.Event()
    started = threading.Event()

    def blocked() -> None:
        started.set()
        release.wait(1.0)

    task = asyncio.create_task(executor.run(blocked))
    assert await asyncio.to_thread(started.wait, 0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert executor.snapshot().active == 1
    with pytest.raises(ExecutorOverloaded):
        await executor.run(lambda: None)

    release.set()
    for _ in range(50):
        if executor.snapshot().active == 0:
            break
        await asyncio.sleep(0.01)
    assert await executor.run(lambda: "ok") == "ok"
    assert await executor.shutdown()


@pytest.mark.asyncio
async def test_context_survives_offload_and_shutdown_drains() -> None:
    trace_id: ContextVar[str] = ContextVar("trace_id", default="missing")
    token = trace_id.set("trace-123")
    executor = BoundedExecutor(
        service="embedding",
        pool="test",
        max_workers=1,
        queue_bound=0,
        submit_timeout_seconds=0.1,
    )
    try:
        assert await executor.run(trace_id.get, stage="embedding_query") == "trace-123"
        started = threading.Event()

        def slow() -> None:
            started.set()
            time.sleep(0.02)

        work = asyncio.create_task(executor.run(slow))
        assert await asyncio.to_thread(started.wait, 0.5)
        assert await executor.shutdown()
        await work
        assert executor.snapshot().closed
    finally:
        trace_id.reset(token)


@pytest.mark.asyncio
async def test_handler_failure_releases_capacity_and_metrics_track_admission() -> None:
    service = "vector_db"
    pool = "failure-contract"
    submitted = METRICS.executor_tasks_submitted_total.labels(
        service=service,
        pool=pool,
    )
    rejected = METRICS.executor_tasks_rejected_total.labels(
        service=service,
        pool=pool,
    )
    submitted_before = submitted._value.get()
    rejected_before = rejected._value.get()
    executor = BoundedExecutor(
        service=service,
        pool=pool,
        max_workers=1,
        queue_bound=1,
        submit_timeout_seconds=0.1,
    )
    release = threading.Event()
    started = threading.Event()

    def blocked() -> str:
        started.set()
        release.wait(1.0)
        return "done"

    def fail() -> None:
        raise ValueError("handler failed")

    active = asyncio.create_task(executor.run(blocked))
    assert await asyncio.to_thread(started.wait, 0.5)
    failed = asyncio.create_task(executor.run(fail))
    for _ in range(50):
        if executor.snapshot().queued == 1:
            break
        await asyncio.sleep(0.01)

    assert executor.snapshot().queued == 1
    assert METRICS.executor_queue_depth.labels(
        service=service,
        pool=pool,
    )._value.get() == 1
    assert submitted._value.get() == submitted_before + 2

    release.set()
    assert await active == "done"
    with pytest.raises(ValueError, match="handler failed"):
        await failed
    assert executor.snapshot().active == 0
    assert executor.snapshot().queued == 0
    assert await executor.run(lambda: "capacity-released") == "capacity-released"

    assert await executor.shutdown()
    with pytest.raises(ExecutorOverloaded) as error:
        await executor.run(lambda: None)
    assert error.value.reason == "closed"
    assert rejected._value.get() == rejected_before + 1
