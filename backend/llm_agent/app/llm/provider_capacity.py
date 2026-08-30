"""Process-wide, fair admission for synchronous vLLM inference calls."""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Condition
from typing import Iterator

from shared.metrics import (
    METRICS,
    TRAFFIC_CLASS_EVAL,
    TRAFFIC_CLASS_LIVE,
    traffic_class,
)

from app.llm.interfaces import ProviderOverloadedError


@dataclass(frozen=True)
class ProviderCapacitySnapshot:
    """Exact admission state for health checks and focused regression tests."""

    limit: int
    inflight: int
    live_inflight: int
    eval_inflight: int
    live_waiting: int
    eval_waiting: int
    closed: bool


class ProviderCapacity:
    """Bound total inference while guaranteeing progress to live and eval work.

    With capacity above one, eval may use at most ``limit - 1`` slots, leaving
    live traffic a reserved slot. When eval is waiting, live callers likewise
    leave one slot for eval. At capacity one, the preferred class alternates
    whenever both classes are queued.
    """

    def __init__(self, *, service: str, limit: int, admission_timeout: float) -> None:
        if limit < 1:
            raise ValueError("provider limit must be at least 1")
        if admission_timeout <= 0:
            raise ValueError("provider admission timeout must be positive")
        self.service = service
        self.limit = limit
        self.admission_timeout = admission_timeout
        self._condition = Condition()
        self._active = {TRAFFIC_CLASS_LIVE: 0, TRAFFIC_CLASS_EVAL: 0}
        self._waiting = {TRAFFIC_CLASS_LIVE: 0, TRAFFIC_CLASS_EVAL: 0}
        self._preferred = TRAFFIC_CLASS_LIVE
        self._closed = False
        METRICS.vllm_configured_limit.labels(service=service).set(limit)
        METRICS.vllm_inflight_requests.labels(service=service).set(0)

    @contextmanager
    def admit(self) -> Iterator[str]:
        """Acquire shared capacity for the trusted current traffic class."""
        request_class = traffic_class()
        started = time.perf_counter()
        admitted = False
        with self._condition:
            self._waiting[request_class] += 1
            try:
                deadline = started + self.admission_timeout
                while not self._can_admit(request_class):
                    if self._closed:
                        self._record(request_class, "closed")
                        raise ProviderOverloadedError("vLLM provider is shutting down")
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        self._record(request_class, "timeout")
                        raise ProviderOverloadedError(
                            "vLLM provider admission timed out before capacity was available"
                        )
                    self._condition.wait(remaining)
                self._waiting[request_class] -= 1
                self._active[request_class] += 1
                admitted = True
                wait = time.perf_counter() - started
                METRICS.vllm_admission_wait_seconds.labels(
                    service=self.service,
                    traffic_class=request_class,
                ).observe(wait)
                self._record(request_class, "admitted")
                METRICS.vllm_inflight_requests.labels(service=self.service).inc()
            except BaseException:
                if not admitted:
                    self._waiting[request_class] -= 1
                    self._condition.notify_all()
                raise

        try:
            yield request_class
        except BaseException as exc:
            status = "failed" if isinstance(exc, Exception) else "cancelled"
            self._record(request_class, status)
            raise
        finally:
            with self._condition:
                self._active[request_class] -= 1
                other = self._other(request_class)
                if self.limit == 1 and self._waiting[other]:
                    self._preferred = other
                METRICS.vllm_inflight_requests.labels(service=self.service).dec()
                self._condition.notify_all()

    def snapshot(self) -> ProviderCapacitySnapshot:
        with self._condition:
            return ProviderCapacitySnapshot(
                limit=self.limit,
                inflight=sum(self._active.values()),
                live_inflight=self._active[TRAFFIC_CLASS_LIVE],
                eval_inflight=self._active[TRAFFIC_CLASS_EVAL],
                live_waiting=self._waiting[TRAFFIC_CLASS_LIVE],
                eval_waiting=self._waiting[TRAFFIC_CLASS_EVAL],
                closed=self._closed,
            )

    def close(self) -> None:
        """Reject queued/new callers and wake every waiter."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def _can_admit(self, request_class: str) -> bool:
        if self._closed or sum(self._active.values()) >= self.limit:
            return False
        other = self._other(request_class)
        if self.limit == 1:
            return not self._waiting[other] or self._preferred == request_class
        if request_class == TRAFFIC_CLASS_EVAL:
            return self._active[request_class] < self.limit - 1
        if self._waiting[other] and self._active[other] == 0:
            return sum(self._active.values()) < self.limit - 1
        return True

    def _record(self, request_class: str, status: str) -> None:
        METRICS.vllm_admission_outcomes_total.labels(
            service=self.service,
            traffic_class=request_class,
            status=status,
        ).inc()

    @staticmethod
    def _other(request_class: str) -> str:
        if request_class == TRAFFIC_CLASS_EVAL:
            return TRAFFIC_CLASS_LIVE
        return TRAFFIC_CLASS_EVAL
