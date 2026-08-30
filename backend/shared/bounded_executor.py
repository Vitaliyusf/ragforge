"""Bounded, observable offload for synchronous service handlers."""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Optional, TypeVar

from .concurrency_probe import track_stage
from .metrics import METRICS


T = TypeVar("T")


class ExecutorOverloaded(RuntimeError):
    """Raised when a bounded executor cannot admit work before its deadline."""

    def __init__(self, service: str, pool: str, reason: str = "saturated") -> None:
        self.service = service
        self.pool = pool
        self.reason = reason
        super().__init__(f"{service} executor pool {pool!r} is {reason}")


@dataclass(frozen=True)
class BoundedExecutorSnapshot:
    """Exact live state maintained by :class:`BoundedExecutor`."""

    max_workers: int
    queue_bound: int
    active: int
    queued: int
    closed: bool


class BoundedExecutor:
    """Run synchronous callables on an explicitly bounded thread pool."""

    def __init__(
        self,
        *,
        service: str,
        pool: str,
        max_workers: int,
        queue_bound: int,
        submit_timeout_seconds: float,
        shutdown_timeout_seconds: float = 10.0,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if queue_bound < 0:
            raise ValueError("queue_bound cannot be negative")
        if submit_timeout_seconds <= 0:
            raise ValueError("submit_timeout_seconds must be positive")
        if shutdown_timeout_seconds <= 0:
            raise ValueError("shutdown_timeout_seconds must be positive")

        self.service = service
        self.pool = pool
        self.max_workers = max_workers
        self.queue_bound = queue_bound
        self.submit_timeout_seconds = submit_timeout_seconds
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self._capacity = asyncio.Semaphore(max_workers + queue_bound)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"{service}-{pool}",
        )
        self._state_lock = Lock()
        self._active = 0
        self._queued = 0
        self._closed = False
        self._pending: set[asyncio.Future[Any]] = set()

        METRICS.executor_max_workers.labels(service=service, pool=pool).set(max_workers)
        self._publish_state()

    async def run(
        self,
        function: Callable[..., T],
        *args: Any,
        stage: Optional[str] = None,
        **kwargs: Any,
    ) -> T:
        """Admit and execute one callable while preserving the current context."""
        accepted_at = time.perf_counter()
        try:
            await asyncio.wait_for(
                self._capacity.acquire(),
                timeout=self.submit_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            self._record_rejection()
            raise ExecutorOverloaded(self.service, self.pool) from exc

        with self._state_lock:
            if self._closed:
                self._capacity.release()
                self._record_rejection()
                raise ExecutorOverloaded(self.service, self.pool, "closed")
            self._queued += 1
            self._publish_state_locked()

        context = copy_context()
        loop = asyncio.get_running_loop()
        try:
            future = loop.run_in_executor(
                self._executor,
                self._execute,
                context.run,
                function,
                args,
                kwargs,
                stage,
                accepted_at,
            )
        except BaseException:
            with self._state_lock:
                self._queued -= 1
                self._publish_state_locked()
            self._capacity.release()
            raise

        METRICS.executor_tasks_submitted_total.labels(
            service=self.service,
            pool=self.pool,
        ).inc()
        self._pending.add(future)
        future.add_done_callback(self._completed)

        # Shielding prevents request cancellation from marking the asyncio
        # future complete while its thread is still consuming pool capacity.
        return await asyncio.shield(future)

    def snapshot(self) -> BoundedExecutorSnapshot:
        """Return an exact state snapshot for health checks and focused tests."""
        with self._state_lock:
            return BoundedExecutorSnapshot(
                max_workers=self.max_workers,
                queue_bound=self.queue_bound,
                active=self._active,
                queued=self._queued,
                closed=self._closed,
            )

    async def shutdown(self) -> bool:
        """Stop admission and drain accepted work within the shutdown deadline."""
        with self._state_lock:
            self._closed = True

        pending = tuple(self._pending)
        if pending:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *(asyncio.shield(future) for future in pending),
                        return_exceptions=True,
                    ),
                    timeout=self.shutdown_timeout_seconds,
                )
            except asyncio.TimeoutError:
                self._executor.shutdown(wait=False, cancel_futures=True)
                return False

        self._executor.shutdown(wait=True, cancel_futures=True)
        return True

    def _execute(
        self,
        context_runner: Callable[..., T],
        function: Callable[..., T],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        stage: Optional[str],
        accepted_at: float,
    ) -> T:
        with self._state_lock:
            self._queued -= 1
            self._active += 1
            self._publish_state_locked()
        try:
            if stage is None:
                return context_runner(function, *args, **kwargs)
            with track_stage(self.service, stage, accepted_at):
                return context_runner(function, *args, **kwargs)
        finally:
            with self._state_lock:
                self._active -= 1
                self._publish_state_locked()

    def _completed(self, future: asyncio.Future[Any]) -> None:
        self._pending.discard(future)
        self._capacity.release()

    def _record_rejection(self) -> None:
        METRICS.executor_tasks_rejected_total.labels(
            service=self.service,
            pool=self.pool,
        ).inc()

    def _publish_state(self) -> None:
        with self._state_lock:
            self._publish_state_locked()

    def _publish_state_locked(self) -> None:
        METRICS.executor_active_workers.labels(
            service=self.service,
            pool=self.pool,
        ).set(self._active)
        METRICS.executor_queue_depth.labels(
            service=self.service,
            pool=self.pool,
        ).set(self._queued)
