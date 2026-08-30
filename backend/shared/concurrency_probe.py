"""Measurement-only probes for the concurrency baseline (CONC-00).

This module observes saturation. It never controls it: nothing here bounds a
pool, sheds a request, or changes an ordering. Bounded executors and
backpressure belong to `CONC-02`; putting the two in one module would make it
impossible to tell, later, whether a latency change came from the measurement
or from the thing being measured.

Everything is opt-in. Importing this module starts no task and wires no
handler, so a service that has not been instrumented yet behaves exactly as it
did before. That is deliberate — `CONC-00` establishes the contract, and each
later task adopts the probes for the path it owns.

Three shapes cover the required signals:

**Span probes** (:func:`track_stage`, :func:`track_inflight`) wrap a unit of
work and record in-flight count, queue wait and handler duration under one
`stage` label from :data:`shared.metrics.CONCURRENCY_REQUEST_CLASSES`. Queue
wait is passed in rather than measured here, because only the caller knows
when the work was *accepted* — for an RPC handler that is the broker delivery,
for an HTTP handler the middleware entry.

**Pool snapshots** (:func:`snapshot_thread_pool`) read a live
``ThreadPoolExecutor`` into gauges. ``ThreadPoolExecutor`` exposes no public
saturation API, so this reads two private attributes defensively: a CPython
change should degrade the snapshot to ``None``, never raise into a request
path.

**The loop sampler** (:class:`EventLoopLagSampler`) is the one probe that owns
a task of its own, so it is a class the caller starts and stops explicitly.

Unmeasured values are ``None`` and are simply not recorded. A gauge that reads
zero because the value was unavailable is indistinguishable from a healthy
zero, which is the more dangerous of the two — the reading an operator trusts.
"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

from .metrics import METRICS

# How often the loop sampler wakes. Frequent enough to catch a blocking call
# inside one request, cheap enough that the sampler is not itself the load:
# one wakeup every 250ms costs nothing measurable and still puts ~240 samples
# in a one-minute load profile.
DEFAULT_LOOP_SAMPLE_INTERVAL = 0.25


@contextmanager
def track_inflight(service: str, stage: str) -> Iterator[None]:
    """Count one unit of work as in-flight for `stage` while the block runs.

    The decrement runs in a ``finally``, so a handler that raises still leaves
    the gauge correct. A gauge that only counts successful exits drifts upward
    forever and reads as permanent saturation.

    Args:
        service: Recording service name.
        stage: One of ``CONCURRENCY_REQUEST_CLASSES``.
    """
    gauge = METRICS.inflight_by_stage.labels(service=service, stage=stage)
    gauge.inc()
    try:
        yield
    finally:
        gauge.dec()


@contextmanager
def track_stage(
    service: str,
    stage: str,
    accepted_at: Optional[float] = None,
) -> Iterator[None]:
    """Record in-flight count, queue wait and handler duration for one unit of work.

    Args:
        service: Recording service name.
        stage: One of ``CONCURRENCY_REQUEST_CLASSES``.
        accepted_at: ``time.perf_counter()`` reading from when the work was
            accepted — broker delivery, HTTP middleware entry, executor
            submission. ``None`` records no queue wait rather than a zero,
            because "started immediately" and "we never looked" must not be
            the same series.
    """
    if accepted_at is not None:
        wait = max(0.0, time.perf_counter() - accepted_at)
        METRICS.queue_wait_seconds.labels(service=service, stage=stage).observe(wait)
    started = time.perf_counter()
    with track_inflight(service, stage):
        try:
            yield
        finally:
            METRICS.handler_duration_seconds.labels(service=service, stage=stage).observe(
                max(0.0, time.perf_counter() - started)
            )


def record_degraded_path(service: str, stage: str, reason: str) -> None:
    """Count one request that left the fast path.

    `reason` must come from ``DEGRADED_PATH_REASONS``. It is never an
    exception message: a raw exception string as a label is an unbounded
    series, and the exception detail belongs in a log line where it can carry
    the context a metric label must not.
    """
    METRICS.degraded_path_total.labels(service=service, stage=stage, reason=reason).inc()


@dataclass(frozen=True)
class PoolSnapshot:
    """One reading of a thread pool's saturation.

    ``active`` and ``queued`` are ``None`` when the running interpreter does
    not expose them in the shape this module reads.
    """

    max_workers: int
    active: Optional[int]
    queued: Optional[int]


def read_thread_pool(executor: ThreadPoolExecutor) -> PoolSnapshot:
    """Read a live ``ThreadPoolExecutor`` without disturbing it.

    ``ThreadPoolExecutor`` has no public introspection API, so this reads
    ``_threads`` and ``_work_queue`` behind ``getattr`` guards. A CPython
    change makes the affected field ``None`` — a degraded snapshot — rather
    than raising into whatever path asked for it.

    ``active`` is derived as *threads spawned minus items still queued*,
    clamped at zero: the pool spawns threads lazily, so the thread count alone
    over-reports a pool that has gone idle.
    """
    max_workers = int(getattr(executor, "_max_workers", 0) or 0)

    threads = getattr(executor, "_threads", None)
    spawned = len(threads) if threads is not None else None

    work_queue = getattr(executor, "_work_queue", None)
    queued: Optional[int]
    try:
        queued = int(work_queue.qsize()) if work_queue is not None else None
    except (AttributeError, NotImplementedError):
        # qsize() is documented as unreliable/absent on some platforms.
        queued = None

    active: Optional[int]
    if spawned is None or queued is None:
        active = None
    else:
        active = max(0, min(spawned, max_workers or spawned) - queued)

    return PoolSnapshot(max_workers=max_workers, active=active, queued=queued)


def snapshot_thread_pool(service: str, pool: str, executor: ThreadPoolExecutor) -> PoolSnapshot:
    """Read a thread pool and publish it to the executor gauges.

    Args:
        service: Recording service name.
        pool: Fixed operator-chosen pool name ("default", "embedding", ...).
            Never a task description — that would make the series unbounded.

    Returns:
        The snapshot that was recorded, so a caller can log or assert on it.
    """
    snapshot = read_thread_pool(executor)
    METRICS.executor_max_workers.labels(service=service, pool=pool).set(snapshot.max_workers)
    if snapshot.active is not None:
        METRICS.executor_active_workers.labels(service=service, pool=pool).set(snapshot.active)
    if snapshot.queued is not None:
        METRICS.executor_queue_depth.labels(service=service, pool=pool).set(snapshot.queued)
    return snapshot


class EventLoopLagSampler:
    """Sample how far behind an event loop is running.

    The measurement is the classic one: sleep for a known interval and report
    how much longer than that the loop actually took to come back. The excess
    is time the loop spent unable to schedule — a synchronous call on an async
    path, a GIL-bound thread, or simply more work than the loop can carry.

    Owns a task, so the caller starts and stops it explicitly and no import
    side effect can leave one running in a test process.
    """

    def __init__(self, service: str, interval: float = DEFAULT_LOOP_SAMPLE_INTERVAL) -> None:
        self._service = service
        self._interval = interval
        self._task: Optional[asyncio.Task[None]] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Begin sampling on the running loop. Starting twice is a no-op."""
        if self.running:
            return
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        """Cancel the sampler and wait for it to finish."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def sample_once(self) -> float:
        """Take one lag reading, record it, and return it.

        Separated from the loop so the measurement is testable without
        scheduling a background task.
        """
        started = time.perf_counter()
        await asyncio.sleep(self._interval)
        lag = max(0.0, time.perf_counter() - started - self._interval)
        METRICS.event_loop_lag_seconds.labels(service=self._service).observe(lag)
        return lag

    async def _run(self) -> None:
        while True:
            await self.sample_once()
