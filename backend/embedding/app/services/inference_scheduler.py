"""One bounded, process-level micro-batching scheduler for embedding inference.

Before CONC-04 every caller decided its own physical batch: the query RPC
handler called ``encode_batch([text], batch_size=1)`` and the ingestion job
service owned its own batch loop. Two concurrent queries therefore ran two
batch-of-one forward passes, and a query arriving during ingestion waited
behind a whole ingestion batch it could have travelled inside.

This module moves that decision to exactly one place. Callers submit *logical*
items and block on their own future; a single worker thread owns the model,
collects concurrently pending items for a short bounded window, and issues one
``encode_batch`` per physical batch. Nothing about the embedding itself changes
— the same model, the same prefixes, the same normalization, the same vectors.

The scheduler is deliberately thread-based rather than async: both production
callers (the RPC handler running inside a ``BoundedExecutor`` worker, and the
Kafka ingestion consumer thread) are synchronous, and a thread-native design
lets them block on a plain ``concurrent.futures.Future`` without an event loop
in the middle.

Two measured decisions are baked in here, both from the CONC-04 benchmark:

* **A small bounded worker count, not one.** With a single worker every live
  query waits behind whatever forward pass is already running, so an
  interactive query arriving during a 32-chunk ingestion batch paid the whole
  batch (measured live p50 57ms -> 399ms). Before CONC-04 the RPC thread and
  the ingestion thread ran the model concurrently, and collapsing to one
  worker would have been a fairness regression. The workers share one model.
* **The collection window is gated on the scheduler actually being busy.**
  Holding a window open while every worker is idle buys nothing — there is
  spare capacity to run the next arrival immediately — and it cost a lone
  query the full window (measured 14ms -> 31ms). The window is now paid only
  when another forward pass is already in flight, which is exactly when
  combining is worth waiting for.
* **Background may occupy at most ``inference_workers - 1`` workers.** Queue
  priority only orders work that has not started yet. Once ingestion had
  filled every worker, a query arriving a microsecond later was ordered first
  in a queue nobody was free to read, and still paid a whole 32-item forward
  pass (measured mixed-load live p95 699ms against a 332ms physical batch:
  two batches deep). The admission bound below keeps one worker able to pick
  up live work at any moment, so such a query waits for the *window*, not for
  a running batch — measured live p95 132ms. The worker count moved 2 -> 3
  alongside it so the reservation costs a live-capable worker rather than
  half of ingestion capacity.

No forward pass is ever interrupted. This is admission and scheduling
isolation, not preemption: ``SentenceTransformer.encode`` offers no
cancellation point, so the only way to bound how long a live arrival waits is
to stop background from holding every worker in the first place.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Deque, List, Optional, Sequence

from app.embedding.interfaces import IEmbeddingModel
from shared.bounded_executor import ExecutorOverloaded
from shared.logging import ServiceLogger
from shared.metrics import METRICS

#: Interactive work: a query RPC a human is waiting on.
CLASS_LIVE = "live"
#: Deferrable work: ingestion chunks, eval and benchmark traffic.
CLASS_BACKGROUND = "background"

#: The pool name this scheduler reports itself under to executor-shaped
#: dashboards and to :class:`ExecutorOverloaded` consumers.
POOL_NAME = "embedding_inference"

#: Metric ``mode`` values on ``embedding_batch_size``, kept to the existing
#: closed pair. A batch carrying at least one live item is recorded as
#: ``query``: that histogram is what proves interactive requests are now
#: travelling inside larger physical batches.
_MODE_QUERY = "query"
_MODE_INGESTION = "ingestion"

_STAGE_BY_CLASS = {
    CLASS_LIVE: "embedding_query",
    CLASS_BACKGROUND: "embedding_ingestion",
}


class EmbeddingSchedulerOverloaded(ExecutorOverloaded):
    """The bounded pending queue refused one submission.

    Subclasses :class:`ExecutorOverloaded` on purpose: the RabbitMQ RPC
    boundary already translates that type into the typed ``service_overloaded``
    reply, so saturation reaches the caller as backpressure rather than as a
    long timeout.
    """

    def __init__(self, service: str, reason: str = "saturated") -> None:
        super().__init__(service, POOL_NAME, reason)
        self.reason = reason


class EmbeddingSchedulerClosed(RuntimeError):
    """Work was pending or submitted when the scheduler stopped accepting it."""


class EmbeddingSchedulerResultMismatch(RuntimeError):
    """The model returned a different number of vectors than texts submitted.

    Typed separately so the ingestion path can keep treating a count mismatch
    as a non-retryable contract violation rather than a transient model error.
    """


class EmbeddingSchedulerUnavailable(RuntimeError):
    """No usable embedding model is loaded behind this scheduler."""


@dataclass
class _Item:
    """One logical embedding submission and the future that owns its result."""

    text: str
    scheduling_class: str
    future: "Future[List[float]]"
    enqueued_at: float


class EmbeddingScheduler:
    """Own the embedding model and every physical forward pass in the process.

    Batch composition is the scheduler's alone. Callers say *what* to embed and
    under which scheduling class; they never say how many texts should share a
    forward pass.
    """

    def __init__(
        self,
        model: Optional[IEmbeddingModel],
        *,
        service: str,
        max_batch_size: int,
        microbatch_window_ms: float,
        max_pending_items: int,
        admission_timeout_seconds: float,
        inference_timeout_seconds: float,
        inference_workers: int = 2,
        max_background_inflight: Optional[int] = None,
        logger: Optional[ServiceLogger] = None,
    ) -> None:
        if inference_workers < 1:
            raise ValueError("inference_workers must be at least 1")
        if max_batch_size < 1:
            raise ValueError("max_batch_size must be at least 1")
        if microbatch_window_ms < 0:
            raise ValueError("microbatch_window_ms cannot be negative")
        if max_pending_items < max_batch_size:
            raise ValueError("max_pending_items must be at least max_batch_size")
        if admission_timeout_seconds <= 0 or inference_timeout_seconds <= 0:
            raise ValueError("scheduler timeouts must be positive")

        self._model = model
        self.service = service
        self.max_batch_size = max_batch_size
        self.window_seconds = microbatch_window_ms / 1000.0
        self.max_pending_items = max_pending_items
        self.admission_timeout_seconds = admission_timeout_seconds
        self.inference_timeout_seconds = inference_timeout_seconds
        self._logger = logger

        # Fairness, expressed as two reservations rather than a policy engine.
        # `live_reserve` is pending capacity background can never occupy, so a
        # saturating ingestion flood cannot make a query un-admittable.
        # `background_floor` is batch slots live cannot monopolise, so a
        # sustained query flood cannot stall ingestion forever.
        self.live_reserve = max(1, min(max_batch_size, max_pending_items // 2))
        self.background_floor = max(1, max_batch_size // 4)

        # The third reservation, and the one queue ordering cannot express:
        # physical worker capacity background is not allowed to fill. It
        # defaults to one below the worker count, so one worker is always able
        # to start live work without waiting for a running batch to finish,
        # and ingestion keeps the rest of the capacity. It is
        # never zero — background must keep making progress — and never above
        # the worker count, which would make it no bound at all.
        if max_background_inflight is None:
            max_background_inflight = max(1, inference_workers - 1)
        if not 1 <= max_background_inflight <= inference_workers:
            raise ValueError(
                "max_background_inflight must be between 1 and inference_workers"
            )
        self.max_background_inflight = max_background_inflight

        self._condition = threading.Condition()
        self._queues: dict[str, Deque[_Item]] = {
            CLASS_LIVE: deque(),
            CLASS_BACKGROUND: deque(),
        }
        self._closed = False
        self._drain_pending = True
        self._inference_calls = 0
        self._items_embedded = 0
        self._busy_workers = 0
        self._background_inflight = 0
        self.inference_workers = inference_workers
        self._workers = [
            threading.Thread(
                target=self._run,
                name=f"{service}-embedding-inference-{index}",
                daemon=True,
            )
            for index in range(inference_workers)
        ]
        self._started = False
        self._publish_pending()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> "EmbeddingScheduler":
        """Start the single inference worker. Idempotent."""
        if not self._started:
            self._started = True
            for worker in self._workers:
                worker.start()
        return self

    def __enter__(self) -> "EmbeddingScheduler":
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.shutdown()

    def shutdown(self, *, drain: bool = True, timeout: float = 10.0) -> bool:
        """Stop admission, then finish or explicitly fail all pending work.

        Returns True when every accepted item reached a terminal state through
        inference, False when the deadline forced the remainder to be failed.
        No future is ever left pending either way.
        """
        with self._condition:
            self._closed = True
            self._drain_pending = drain
            self._condition.notify_all()

        drained = True
        if self._started:
            deadline = time.monotonic() + timeout
            for worker in self._workers:
                worker.join(timeout=max(0.0, deadline - time.monotonic()))
                drained = drained and not worker.is_alive()

        # Whatever the worker did not reach — because draining was disabled or
        # the deadline expired — is failed here, so no caller waits forever.
        self._fail_remaining(
            EmbeddingSchedulerClosed("embedding inference scheduler is shutting down")
        )
        return drained and self.pending_items() == 0

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """True when a loaded model is behind this scheduler."""
        return self._model is not None and self._model.is_loaded()

    def pending_items(self, scheduling_class: Optional[str] = None) -> int:
        """Exact count of accepted-but-not-yet-embedded items."""
        with self._condition:
            if scheduling_class is not None:
                return len(self._queues[scheduling_class])
            return sum(len(queue) for queue in self._queues.values())

    @property
    def inference_calls(self) -> int:
        """Physical ``encode_batch`` calls issued since process start."""
        return self._inference_calls

    @property
    def background_inflight(self) -> int:
        """Workers currently running a batch that carries background items."""
        with self._condition:
            return self._background_inflight

    @property
    def items_embedded(self) -> int:
        """Logical items that reached a physical forward pass."""
        return self._items_embedded

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def encode(
        self,
        texts: Sequence[str],
        *,
        scheduling_class: str = CLASS_LIVE,
        admission_timeout: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> List[List[float]]:
        """Embed ``texts`` and return their vectors in submission order.

        Each text is a distinct logical item with its own future — identical
        texts are never deduplicated, because callers rely on getting exactly
        as many vectors as they submitted, in order.
        """
        if scheduling_class not in self._queues:
            raise ValueError(f"unknown scheduling class: {scheduling_class!r}")
        if not texts:
            return []
        if not self.is_available():
            raise EmbeddingSchedulerUnavailable("Embedding model not available")

        items = [
            _Item(text=text, scheduling_class=scheduling_class, future=Future(), enqueued_at=0.0)
            for text in texts
        ]
        admission_deadline = time.monotonic() + (
            admission_timeout if admission_timeout is not None else self.admission_timeout_seconds
        )
        self._admit(items, admission_deadline)

        result_deadline = time.monotonic() + (
            timeout if timeout is not None else self.inference_timeout_seconds
        )
        results: List[List[float]] = []
        try:
            for item in items:
                remaining = result_deadline - time.monotonic()
                if remaining <= 0:
                    self._record_timeout(scheduling_class, "inference")
                    raise TimeoutError("embedding inference deadline expired")
                try:
                    results.append(item.future.result(timeout=remaining))
                except TimeoutError:
                    self._record_timeout(scheduling_class, "inference")
                    raise
        except BaseException:
            # Cancelling only removes items that have not entered a batch;
            # anything already composed keeps its slot, so no neighbouring
            # item's result index can shift underneath it.
            for item in items:
                item.future.cancel()
            raise
        return results

    def encode_one(
        self,
        text: str,
        *,
        scheduling_class: str = CLASS_LIVE,
        admission_timeout: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> List[float]:
        """Embed exactly one text — the query RPC shape."""
        vectors = self.encode(
            [text],
            scheduling_class=scheduling_class,
            admission_timeout=admission_timeout,
            timeout=timeout,
        )
        return vectors[0] if vectors else []

    def _admit(self, items: List[_Item], deadline: float) -> None:
        """Take pending capacity for a whole submission, or refuse it typed."""
        count = len(items)
        scheduling_class = items[0].scheduling_class
        limit = self._pending_limit(scheduling_class)
        if count > limit:
            self._record_rejection(scheduling_class, "oversized")
            raise EmbeddingSchedulerOverloaded(self.service, "oversized")

        with self._condition:
            while True:
                if self._closed:
                    self._record_rejection(scheduling_class, "closed")
                    raise EmbeddingSchedulerOverloaded(self.service, "closed")
                if self._total_pending_locked() + count <= limit:
                    now = time.monotonic()
                    queue = self._queues[scheduling_class]
                    for item in items:
                        item.enqueued_at = now
                        queue.append(item)
                    self._publish_pending_locked()
                    self._condition.notify_all()
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._record_timeout(scheduling_class, "admission")
                    self._record_rejection(scheduling_class, "saturated")
                    raise EmbeddingSchedulerOverloaded(self.service, "saturated")
                self._condition.wait(remaining)

    def _pending_limit(self, scheduling_class: str) -> int:
        """Global bound for live; the same bound minus the live reservation."""
        if scheduling_class == CLASS_LIVE:
            return self.max_pending_items
        return max(1, self.max_pending_items - self.live_reserve)

    # ------------------------------------------------------------------
    # Inference worker
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while True:
            batch = self._collect_batch()
            if batch is None:
                return
            if not batch:
                continue
            # `_collect_batch` already claimed this worker's capacity — and,
            # for a batch carrying background items, the background slot —
            # under the same lock that composed the batch, so two workers can
            # never both decide they are the one allowed background runner.
            try:
                self._run_batch(batch)
            finally:
                with self._condition:
                    self._busy_workers -= 1
                    if _carries_background(batch):
                        self._background_inflight -= 1
                    self._condition.notify_all()

    def _collect_batch(self) -> Optional[List[_Item]]:
        """Block for the first item, then hold the micro-batch window open.

        Returns None when the scheduler is finished and the worker should exit.
        """
        with self._condition:
            while True:
                if self._closed and (
                    not self._drain_pending or not self._total_pending_locked()
                ):
                    return None
                if self._queues[CLASS_LIVE] or self._background_admissible_locked():
                    break
                # Either nothing is pending, or the only pending work is
                # background and every background slot is taken. Both are
                # resolved by another worker finishing, which notifies here.
                self._condition.wait()

            # Only pay the window when another forward pass is already in
            # flight. An idle scheduler has capacity to serve the next arrival
            # on its own, so waiting would be pure added latency.
            #
            # The window is measured from the first pending item, not from the
            # last arrival, so a steady arrival stream cannot extend it.
            deadline = time.monotonic() + self.window_seconds
            while (
                self._busy_workers > 0
                and self._total_pending_locked() < self.max_batch_size
                and not self._closed
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)

            batch = self._compose_locked()
            if batch:
                self._busy_workers += 1
                if _carries_background(batch):
                    self._background_inflight += 1
            return batch

    def _background_admissible_locked(self) -> bool:
        """True when this worker may start a batch carrying background items."""
        return (
            bool(self._queues[CLASS_BACKGROUND])
            and self._background_inflight < self.max_background_inflight
        )

    def _compose_locked(self) -> List[_Item]:
        """Fill one physical batch under the live-first, background-floor rule.

        Background is taken only while a background worker slot is free. Once
        it is not, this worker composes a live-only batch — or none at all,
        and parks — which is exactly what keeps a worker free to pick up a
        live arrival while a long ingestion forward pass is still running.
        """
        batch: List[_Item] = []
        allow_background = self._background_admissible_locked()
        reserved = self.background_floor if allow_background else 0
        live_capacity = max(self.max_batch_size - reserved, 0)

        self._take_locked(batch, CLASS_LIVE, live_capacity)
        if allow_background:
            self._take_locked(batch, CLASS_BACKGROUND, self.max_batch_size - len(batch))
        # Live may reclaim slots the background queue did not actually use.
        self._take_locked(batch, CLASS_LIVE, self.max_batch_size - len(batch))

        self._publish_pending_locked()
        # Admission capacity was just freed.
        self._condition.notify_all()
        return batch

    def _take_locked(self, batch: List[_Item], scheduling_class: str, capacity: int) -> None:
        queue = self._queues[scheduling_class]
        while len(batch) < self.max_batch_size and capacity > 0 and queue:
            item = queue.popleft()
            # A caller that timed out or was cancelled marked its future; it is
            # dropped here, before it is given a position in the batch.
            if not item.future.set_running_or_notify_cancel():
                continue
            batch.append(item)
            capacity -= 1

    def _run_batch(self, batch: List[_Item]) -> None:
        assert self._model is not None  # admission requires a loaded model
        texts = [item.text for item in batch]
        now = time.monotonic()
        for item in batch:
            METRICS.queue_wait_seconds.labels(
                service=self.service,
                stage=_STAGE_BY_CLASS[item.scheduling_class],
            ).observe(max(0.0, now - item.enqueued_at))

        mode = (
            _MODE_QUERY
            if any(item.scheduling_class == CLASS_LIVE for item in batch)
            else _MODE_INGESTION
        )
        METRICS.embedding_batch_size.labels(service=self.service, mode=mode).observe(len(batch))
        with self._condition:
            self._inference_calls += 1

        started = time.monotonic()
        try:
            vectors = self._model.encode_batch(texts, batch_size=len(texts))
        except Exception as exc:  # one failed forward pass, every waiter told
            self._complete_batch_with_error(batch, exc)
            return
        finally:
            METRICS.embedding_inference_duration_seconds.labels(
                service=self.service,
            ).observe(time.monotonic() - started)

        if len(vectors) != len(texts):
            self._complete_batch_with_error(
                batch,
                EmbeddingSchedulerResultMismatch(
                    f"expected {len(texts)} vectors, got {len(vectors)}"
                ),
            )
            return

        with self._condition:
            self._items_embedded += len(batch)
        for scheduling_class in self._queues:
            embedded = sum(
                1 for item in batch if item.scheduling_class == scheduling_class
            )
            if embedded:
                METRICS.embedding_scheduler_items_total.labels(
                    service=self.service,
                    embedding_class=scheduling_class,
                ).inc(embedded)
        settled = time.monotonic()
        for item in batch:
            METRICS.embedding_scheduler_latency_seconds.labels(
                service=self.service,
                embedding_class=item.scheduling_class,
            ).observe(max(0.0, settled - item.enqueued_at))
        for item, vector in zip(batch, vectors):
            _settle(item.future, vector, None)

    def _complete_batch_with_error(self, batch: List[_Item], error: BaseException) -> None:
        for item in batch:
            _settle(item.future, None, error)
        if self._logger is not None:
            self._logger.log(
                "embedding_scheduler:batch",
                "Embedding batch failed",
                {
                    "batch_size": len(batch),
                    "error": str(error),
                    "error_type": type(error).__name__,
                },
                hypothesis_id="E",
            )

    def _fail_remaining(self, error: BaseException) -> None:
        with self._condition:
            leftover = [item for queue in self._queues.values() for item in queue]
            for queue in self._queues.values():
                queue.clear()
            self._publish_pending_locked()
            self._condition.notify_all()
        for item in leftover:
            item.future.set_running_or_notify_cancel()
            _settle(item.future, None, error)

    # ------------------------------------------------------------------
    # Metrics helpers
    # ------------------------------------------------------------------

    def _total_pending_locked(self) -> int:
        return sum(len(queue) for queue in self._queues.values())

    def _publish_pending(self) -> None:
        with self._condition:
            self._publish_pending_locked()

    def _publish_pending_locked(self) -> None:
        for scheduling_class, queue in self._queues.items():
            METRICS.embedding_scheduler_pending_items.labels(
                service=self.service,
                embedding_class=scheduling_class,
            ).set(len(queue))

    def _record_timeout(self, scheduling_class: str, phase: str) -> None:
        METRICS.embedding_scheduler_timeouts_total.labels(
            service=self.service,
            embedding_class=scheduling_class,
            phase=phase,
        ).inc()

    def _record_rejection(self, scheduling_class: str, reason: str) -> None:
        METRICS.embedding_scheduler_rejected_total.labels(
            service=self.service,
            embedding_class=scheduling_class,
            reason=reason,
        ).inc()


def _carries_background(batch: List[_Item]) -> bool:
    """True when this physical batch holds any deferrable item."""
    return any(item.scheduling_class == CLASS_BACKGROUND for item in batch)


def _settle(
    future: "Future[List[float]]",
    result: Optional[List[float]],
    error: Optional[BaseException],
) -> None:
    """Complete one future, tolerating a caller that already abandoned it."""
    try:
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result or [])
    except Exception:
        # The future was already cancelled/settled by its caller. Nothing is
        # leaked: a settled future is a terminal state.
        pass


def create_scheduler(
    model: Optional[IEmbeddingModel],
    config: object,
    logger: Optional[ServiceLogger] = None,
) -> EmbeddingScheduler:
    """Build the one process-level scheduler from service configuration."""
    workers = max(1, int(getattr(config, "embedding_inference_workers", 2)))
    return EmbeddingScheduler(
        model,
        service=getattr(config, "service_name", "embedding"),
        max_batch_size=max(1, int(getattr(config, "embedding_max_batch_size", 32))),
        microbatch_window_ms=float(getattr(config, "embedding_microbatch_window_ms", 5.0)),
        max_pending_items=int(getattr(config, "embedding_max_pending_items", 256)),
        admission_timeout_seconds=float(
            getattr(config, "embedding_admission_timeout_seconds", 1.0)
        ),
        inference_timeout_seconds=float(
            getattr(config, "embedding_inference_timeout_seconds", 30.0)
        ),
        inference_workers=workers,
        max_background_inflight=max(
            1,
            min(
                workers,
                int(
                    getattr(
                        config,
                        "embedding_max_background_inflight",
                        max(1, workers - 1),
                    )
                ),
            ),
        ),
        logger=logger,
    )
