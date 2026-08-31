"""One bounded, process-level scheduler for learned cross-encoder reranking.

Before CONC-05 the reranker owned a ``ThreadPoolExecutor(max_workers=1)`` and a
single ``_inflight`` future. A second concurrent turn found that future
unfinished, was answered ``busy``, and its pipeline fell back to the fused
RRF ordering. The same query over the same corpus therefore returned a
*different* final ranking depending on whether another request happened to be
reranking at that moment — a quality regression that no latency number shows.

This module removes that coupling. Callers submit one logical rerank request —
a query plus its candidate passages — and await their own future. A small
bounded set of worker threads shares the single model, collects concurrently
pending requests for a short window, and flattens their ``(query, passage)``
pairs into one physical forward pass. Scores are fanned back out by exact
offsets, so a batch is an implementation detail no caller can observe.

Three properties are load-bearing:

* **A request is never refused because another one is running.** Contention
  produces queueing, not degradation. ``busy`` survives only as the explicit
  answer when the bounded pending queue cannot admit the request before its
  admission deadline — real overload, which an operator can now tell apart
  from ordinary concurrency because the two have different metrics.
* **Batching is opportunistic, not waited for.** The window defaults to zero
  and is paid only when a forward pass is already in flight. A cross-encoder
  runs one full forward pass per pair, so per-pair compute dominates per-call
  overhead and there is little for a window to amortise: the CONC-05 probe
  measured a 5ms window buying no throughput in that cost shape while raising
  live p95. What remains is free — a worker picking up a batch takes whatever
  is already queued — and that is kept.
* **Background may occupy at most ``inference_workers - 1`` workers.** Queue
  priority only orders work that has not started. Once eval traffic fills
  every worker, an interactive turn arriving a microsecond later is ordered
  first in a queue nobody is free to read and still waits out a whole forward
  pass. The reservation keeps one worker able to pick up live work at any
  moment.

The model itself is not owned here. The scheduler is handed a ``predict``
callable, so this module stays free of ``sentence_transformers`` and the
reranker keeps its single model instance, its pinned revision and its
``batch_size``/``max_length`` contract exactly as before. Nothing about how a
pair is scored changes: the same model scores the same pairs, and each pair is
scored independently of which request it travelled with.

No forward pass is ever interrupted. This is admission and scheduling
isolation, not preemption: ``CrossEncoder.predict`` offers no cancellation
point, so a cancelled request is dropped before it is composed into a batch or
not at all.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

from shared.bounded_executor import ExecutorOverloaded
from shared.logging import ServiceLogger
from shared.metrics import METRICS

#: Interactive work: a retrieval turn a human is waiting on.
CLASS_LIVE = "live"
#: Deferrable work: eval runs, benchmark phases, background scoring.
CLASS_BACKGROUND = "background"

#: The pool name this scheduler reports itself under to executor-shaped
#: dashboards and to :class:`ExecutorOverloaded` consumers.
POOL_NAME = "reranker_inference"

#: ``traffic_class`` values the RAG pipeline already produces, mapped onto the
#: two scheduling classes. Anything that is not an interactive turn is
#: deferrable, so an unknown class degrades to background rather than
#: competing with a user's turn.
def scheduling_class_for(traffic_class: str) -> str:
    """Map the pipeline's fixed traffic class onto a scheduling class."""
    return CLASS_LIVE if traffic_class == "live" else CLASS_BACKGROUND


class RerankSchedulerOverloaded(ExecutorOverloaded):
    """The bounded pending queue could not admit one rerank request.

    Subclasses :class:`ExecutorOverloaded` on purpose: overload reaches the
    rest of the system through the same typed backpressure channel every other
    bounded pool in this repository uses.
    """

    def __init__(self, service: str, reason: str = "saturated") -> None:
        super().__init__(service, POOL_NAME, reason)
        self.reason = reason


class RerankSchedulerClosed(RuntimeError):
    """Work was pending or submitted when the scheduler stopped accepting it."""


class RerankScoreCountMismatch(RuntimeError):
    """The model returned a different number of scores than pairs submitted.

    Typed separately because it is a contract violation, not a transient model
    error: retrying the same pairs against the same model cannot fix it.
    """


@dataclass
class _Request:
    """One logical rerank submission and the future that owns its scores."""

    query: str
    passages: List[str]
    scheduling_class: str
    future: "Future[List[float]]" = field(default_factory=Future)
    enqueued_at: float = 0.0

    @property
    def pairs(self) -> int:
        """Physical ``(query, passage)`` pairs this request contributes."""
        return len(self.passages)


class RerankScheduler:
    """Own every physical reranker forward pass in the process.

    Batch composition belongs to the scheduler alone. Callers say *what* to
    score and under which scheduling class; they never say which pairs should
    share a forward pass, and they cannot observe the answer.
    """

    def __init__(
        self,
        predict: Callable[[List[Tuple[str, str]]], List[float]],
        *,
        service: str,
        max_batch_pairs: int,
        microbatch_window_ms: float,
        max_pending_pairs: int,
        admission_timeout_seconds: float,
        inference_workers: int = 2,
        max_background_inflight: Optional[int] = None,
        logger: Optional[ServiceLogger] = None,
    ) -> None:
        if inference_workers < 1:
            raise ValueError("inference_workers must be at least 1")
        if max_batch_pairs < 1:
            raise ValueError("max_batch_pairs must be at least 1")
        if microbatch_window_ms < 0:
            raise ValueError("microbatch_window_ms cannot be negative")
        if max_pending_pairs < max_batch_pairs:
            raise ValueError("max_pending_pairs must be at least max_batch_pairs")
        if admission_timeout_seconds <= 0:
            raise ValueError("admission_timeout_seconds must be positive")

        self._predict = predict
        self.service = service
        self.max_batch_pairs = max_batch_pairs
        self.window_seconds = microbatch_window_ms / 1000.0
        self.max_pending_pairs = max_pending_pairs
        self.admission_timeout_seconds = admission_timeout_seconds
        self._logger = logger

        # Fairness as two reservations rather than a policy engine.
        # `live_reserve` is pending capacity background can never occupy, so an
        # eval flood cannot make an interactive turn un-admittable.
        # `background_floor` is batch pairs live cannot monopolise, so a
        # sustained live flood cannot stall eval work forever.
        self.live_reserve = max(1, min(max_batch_pairs, max_pending_pairs // 2))
        self.background_floor = max(1, max_batch_pairs // 4)

        # The reservation queue ordering cannot express: physical worker
        # capacity background may not fill. One below the worker count, so a
        # live arrival always has somewhere to run; never zero, because
        # background must keep making progress.
        if max_background_inflight is None:
            max_background_inflight = max(1, inference_workers - 1)
        if not 1 <= max_background_inflight <= inference_workers:
            raise ValueError(
                "max_background_inflight must be between 1 and inference_workers"
            )
        self.max_background_inflight = max_background_inflight
        self.inference_workers = inference_workers

        self._condition = threading.Condition()
        self._queues: Dict[str, Deque[_Request]] = {
            CLASS_LIVE: deque(),
            CLASS_BACKGROUND: deque(),
        }
        self._pending_pairs: Dict[str, int] = {CLASS_LIVE: 0, CLASS_BACKGROUND: 0}
        # Event-loop-side waiters for pending capacity. Admission must never
        # block the loop, so a saturated submitter parks on an asyncio future
        # that a worker thread resolves through `call_soon_threadsafe`.
        self._capacity_waiters: List[Tuple[asyncio.AbstractEventLoop, "asyncio.Future[None]"]] = []
        self._closed = False
        self._drain_pending = True
        self._inference_calls = 0
        self._pairs_scored = 0
        self._busy_workers = 0
        self._background_inflight = 0
        self._workers = [
            threading.Thread(
                target=self._run,
                name=f"{service}-reranker-inference-{index}",
                daemon=True,
            )
            for index in range(inference_workers)
        ]
        self._started = False
        self._publish_capacity()
        self._publish_pending()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> "RerankScheduler":
        """Start the inference workers. Idempotent and cheap to re-call."""
        if self._started:
            return self
        with self._condition:
            if self._started:
                return self
            self._started = True
            workers = list(self._workers)
        for worker in workers:
            worker.start()
        return self

    def __enter__(self) -> "RerankScheduler":
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.shutdown()

    def shutdown(self, *, drain: bool = True, timeout: float = 10.0) -> bool:
        """Stop admission, then finish or explicitly fail all pending work.

        Returns True when every accepted request reached a terminal state
        through inference, False when the deadline forced the remainder to be
        failed. No future is left pending either way, and no caller waits
        forever on a process that is going away.
        """
        with self._condition:
            self._closed = True
            self._drain_pending = drain
            self._condition.notify_all()
            self._notify_capacity_locked()

        drained = True
        if self._started:
            deadline = time.monotonic() + timeout
            for worker in self._workers:
                worker.join(timeout=max(0.0, deadline - time.monotonic()))
                drained = drained and not worker.is_alive()

        # Whatever the workers did not reach — because draining was disabled or
        # the deadline expired — is failed here explicitly.
        self._fail_remaining(
            RerankSchedulerClosed("reranker inference scheduler is shutting down")
        )
        return drained and self.pending_requests() == 0

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def pending_pairs(self, scheduling_class: Optional[str] = None) -> int:
        """Accepted-but-not-yet-scored ``(query, passage)`` pairs."""
        with self._condition:
            if scheduling_class is not None:
                return self._pending_pairs[scheduling_class]
            return sum(self._pending_pairs.values())

    def pending_requests(self, scheduling_class: Optional[str] = None) -> int:
        """Accepted-but-not-yet-scored logical requests."""
        with self._condition:
            if scheduling_class is not None:
                return len(self._queues[scheduling_class])
            return sum(len(queue) for queue in self._queues.values())

    @property
    def inference_calls(self) -> int:
        """Physical model calls issued since process start."""
        return self._inference_calls

    @property
    def pairs_scored(self) -> int:
        """Pairs that reached a physical forward pass."""
        return self._pairs_scored

    @property
    def background_inflight(self) -> int:
        """Workers currently running a batch that carries background work."""
        with self._condition:
            return self._background_inflight

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    async def submit(
        self,
        query: str,
        passages: Sequence[str],
        *,
        scheduling_class: str = CLASS_LIVE,
        admission_timeout: Optional[float] = None,
    ) -> "Future[List[float]]":
        """Accept one rerank request and return the future owning its scores.

        The returned future resolves to exactly ``len(passages)`` scores in
        submission order. Identical passages are never deduplicated: a caller
        relies on getting one score per candidate position it submitted.

        Raises :class:`RerankSchedulerOverloaded` when the bounded pending
        queue cannot take the request before the admission deadline. That —
        and only that — is overload; waiting behind another request is not.
        """
        if scheduling_class not in self._queues:
            raise ValueError(f"unknown scheduling class: {scheduling_class!r}")
        if not passages:
            raise ValueError("a rerank request needs at least one passage")

        request = _Request(
            query=query,
            passages=list(passages),
            scheduling_class=scheduling_class,
        )
        deadline = time.monotonic() + (
            admission_timeout
            if admission_timeout is not None
            else self.admission_timeout_seconds
        )
        await self._admit(request, deadline)
        return request.future

    async def _admit(self, request: _Request, deadline: float) -> None:
        """Take pending capacity for the request, or refuse it typed.

        Never blocks the event loop: the fast path takes a short lock, and a
        saturated submitter awaits an asyncio future a worker thread resolves
        once pairs leave the queue.
        """
        scheduling_class = request.scheduling_class
        # A request larger than its class limit is never refused for its own
        # size — the pipeline bounds candidates already, and refusing here
        # would silently disable reranking for a legitimate shape. It simply
        # waits for the queue to be empty enough to hold it alone.
        limit = max(self._pending_limit(scheduling_class), request.pairs)
        loop = asyncio.get_running_loop()

        while True:
            with self._condition:
                if self._closed:
                    self._record_rejection(scheduling_class, "closed")
                    raise RerankSchedulerOverloaded(self.service, "closed")
                if self._total_pending_pairs_locked() + request.pairs <= limit:
                    request.enqueued_at = time.monotonic()
                    self._queues[scheduling_class].append(request)
                    self._pending_pairs[scheduling_class] += request.pairs
                    self._publish_pending_locked()
                    self._condition.notify_all()
                    return
                waiter: "asyncio.Future[None]" = loop.create_future()
                self._capacity_waiters.append((loop, waiter))

            remaining = deadline - time.monotonic()
            try:
                if remaining <= 0:
                    raise asyncio.TimeoutError
                await asyncio.wait_for(waiter, remaining)
            except (asyncio.TimeoutError, TimeoutError):
                self._discard_waiter(waiter)
                self._record_timeout(scheduling_class, "admission")
                self._record_rejection(scheduling_class, "saturated")
                raise RerankSchedulerOverloaded(self.service, "saturated") from None
            except BaseException:
                # The caller was cancelled while parked. Leaving the waiter
                # registered would have a worker thread resolve a future
                # nobody reads, so it is unregistered on every exit path.
                self._discard_waiter(waiter)
                raise
            else:
                self._discard_waiter(waiter)

    def _pending_limit(self, scheduling_class: str) -> int:
        """The global bound for live; the same bound minus the live reserve."""
        if scheduling_class == CLASS_LIVE:
            return self.max_pending_pairs
        return max(1, self.max_pending_pairs - self.live_reserve)

    def _discard_waiter(self, waiter: "asyncio.Future[None]") -> None:
        with self._condition:
            self._capacity_waiters = [
                entry for entry in self._capacity_waiters if entry[1] is not waiter
            ]

    def _notify_capacity_locked(self) -> None:
        """Wake every parked submitter. Called whenever pending pairs drop."""
        waiters, self._capacity_waiters = self._capacity_waiters, []
        for loop, waiter in waiters:
            try:
                loop.call_soon_threadsafe(_resolve, waiter)
            except RuntimeError:
                # The submitter's loop is already closed; its future can no
                # longer be awaited by anyone, so there is nothing to release.
                pass

    # ------------------------------------------------------------------
    # Inference workers
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while True:
            batch = self._collect_batch()
            if batch is None:
                return
            if not batch:
                continue
            # `_collect_batch` claimed this worker's capacity — and, for a
            # batch carrying background work, the background slot — under the
            # same lock that composed the batch, so two workers can never both
            # decide they are the one allowed background runner.
            try:
                self._run_batch(batch)
            finally:
                with self._condition:
                    self._busy_workers -= 1
                    if _carries_background(batch):
                        self._background_inflight -= 1
                    self._condition.notify_all()

    def _collect_batch(self) -> Optional[List[_Request]]:
        """Block for the first request, then hold the micro-batch window open.

        Returns None when the scheduler is finished and the worker should exit.
        """
        with self._condition:
            while True:
                if self._closed and (
                    not self._drain_pending or not self._total_pending_pairs_locked()
                ):
                    return None
                if self._queues[CLASS_LIVE] or self._background_admissible_locked():
                    break
                # Either nothing is pending, or the only pending work is
                # background and every background slot is taken. Both are
                # resolved by another worker finishing, which notifies here.
                self._condition.wait()

            # Pay the window only when another forward pass is already in
            # flight: an idle scheduler can serve this arrival on its own, so
            # waiting would be latency bought for nothing. Measured from the
            # first pending request, so a steady arrival stream cannot extend
            # it indefinitely.
            deadline = time.monotonic() + self.window_seconds
            while (
                self._busy_workers > 0
                and self._total_pending_pairs_locked() < self.max_batch_pairs
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
        """True when this worker may start a batch carrying background work."""
        return (
            bool(self._queues[CLASS_BACKGROUND])
            and self._background_inflight < self.max_background_inflight
        )

    def _compose_locked(self) -> List[_Request]:
        """Fill one physical batch under the live-first, background-floor rule.

        Background is taken only while a background worker slot is free. Once
        it is not, this worker composes a live-only batch — or none at all and
        parks — which is what keeps a worker able to pick up a live arrival
        while a long background forward pass is still running.
        """
        batch: List[_Request] = []
        allow_background = self._background_admissible_locked()
        reserved = self.background_floor if allow_background else 0
        live_budget = max(self.max_batch_pairs - reserved, 0)

        self._take_locked(batch, CLASS_LIVE, live_budget)
        if allow_background:
            self._take_locked(batch, CLASS_BACKGROUND, self.max_batch_pairs)
        # Live may reclaim the pairs the background queue did not actually use.
        self._take_locked(batch, CLASS_LIVE, self.max_batch_pairs)

        self._publish_pending_locked()
        # Admission capacity was just freed for both the thread-side waiters
        # and the event-loop-side ones.
        self._condition.notify_all()
        self._notify_capacity_locked()
        return batch

    def _take_locked(
        self, batch: List[_Request], scheduling_class: str, pair_budget: int
    ) -> None:
        """Move whole requests from one queue into the batch, in FIFO order.

        A request is never split across forward passes: its scores must come
        back as one contiguous slice, and splitting would buy nothing but a
        second place for the offsets to go wrong. When the head does not fit,
        this take stops rather than skipping it, so a large request cannot be
        starved by a stream of small ones behind it.
        """
        queue = self._queues[scheduling_class]
        pairs = _batch_pairs(batch)
        while queue:
            head = queue[0]
            if batch and pairs + head.pairs > min(pair_budget, self.max_batch_pairs):
                return
            queue.popleft()
            self._pending_pairs[scheduling_class] -= head.pairs
            # A caller that timed out or was cancelled marked its future. It is
            # dropped here, before it is given a position in the batch, so no
            # surviving request's score offsets can shift underneath it.
            if not head.future.set_running_or_notify_cancel():
                continue
            batch.append(head)
            pairs += head.pairs

    def _run_batch(self, batch: List[_Request]) -> None:
        pairs: List[Tuple[str, str]] = [
            (request.query, passage)
            for request in batch
            for passage in request.passages
        ]
        now = time.monotonic()
        for request in batch:
            METRICS.reranker_scheduler_queue_wait_seconds.labels(
                service=self.service, rerank_class=request.scheduling_class
            ).observe(max(0.0, now - request.enqueued_at))

        METRICS.reranker_batch_size.labels(service=self.service).observe(len(pairs))
        with self._condition:
            self._inference_calls += 1

        started = time.monotonic()
        try:
            scores = self._predict(pairs)
        except BaseException as exc:  # one failed pass, every waiter told
            self._complete_batch_with_error(batch, exc)
            return
        finally:
            METRICS.reranker_inference_duration_seconds.labels(
                service=self.service
            ).observe(time.monotonic() - started)

        if len(scores) != len(pairs):
            self._complete_batch_with_error(
                batch,
                RerankScoreCountMismatch(
                    f"expected {len(pairs)} scores, got {len(scores)}"
                ),
            )
            return

        with self._condition:
            self._pairs_scored += len(pairs)
        for scheduling_class in self._queues:
            scored = sum(
                request.pairs
                for request in batch
                if request.scheduling_class == scheduling_class
            )
            if scored:
                METRICS.reranker_scheduler_pairs_total.labels(
                    service=self.service, rerank_class=scheduling_class
                ).inc(scored)

        # Exact fan-out. Each request owns one contiguous slice at the offset
        # its own pairs were written to, so duplicate passages — within a
        # request or across requests — keep distinct positions.
        offset = 0
        for request in batch:
            _settle(request.future, scores[offset : offset + request.pairs], None)
            offset += request.pairs

    def _complete_batch_with_error(
        self, batch: List[_Request], error: BaseException
    ) -> None:
        for request in batch:
            _settle(request.future, None, error)
        if self._logger is not None:
            self._logger.log(
                "rerank_scheduler:batch",
                "Reranker batch failed",
                {
                    "requests": len(batch),
                    "pairs": sum(request.pairs for request in batch),
                    "error": str(error),
                    "error_type": type(error).__name__,
                },
            )

    def _fail_remaining(self, error: BaseException) -> None:
        with self._condition:
            leftover = [
                request for queue in self._queues.values() for request in queue
            ]
            for scheduling_class, queue in self._queues.items():
                queue.clear()
                self._pending_pairs[scheduling_class] = 0
            self._publish_pending_locked()
            self._condition.notify_all()
            self._notify_capacity_locked()
        for request in leftover:
            request.future.set_running_or_notify_cancel()
            _settle(request.future, None, error)

    # ------------------------------------------------------------------
    # Metrics helpers
    # ------------------------------------------------------------------

    def _total_pending_pairs_locked(self) -> int:
        return sum(self._pending_pairs.values())

    def _publish_pending(self) -> None:
        with self._condition:
            self._publish_pending_locked()

    def _publish_pending_locked(self) -> None:
        for scheduling_class, queue in self._queues.items():
            METRICS.reranker_scheduler_pending_requests.labels(
                service=self.service, rerank_class=scheduling_class
            ).set(len(queue))
            METRICS.reranker_scheduler_pending_pairs.labels(
                service=self.service, rerank_class=scheduling_class
            ).set(self._pending_pairs[scheduling_class])

    def _publish_capacity(self) -> None:
        """Publish the configured bounds so a dashboard can read saturation.

        `setting` is a closed four-value vocabulary, not free text.
        """
        for setting, value in (
            ("max_pending_pairs", self.max_pending_pairs),
            ("max_batch_pairs", self.max_batch_pairs),
            ("inference_workers", self.inference_workers),
            ("max_background_inflight", self.max_background_inflight),
        ):
            METRICS.reranker_scheduler_capacity.labels(
                service=self.service, setting=setting
            ).set(value)

    def _record_timeout(self, scheduling_class: str, phase: str) -> None:
        METRICS.reranker_scheduler_timeouts_total.labels(
            service=self.service, rerank_class=scheduling_class, phase=phase
        ).inc()

    def _record_rejection(self, scheduling_class: str, reason: str) -> None:
        METRICS.reranker_scheduler_rejected_total.labels(
            service=self.service, rerank_class=scheduling_class, reason=reason
        ).inc()


def _batch_pairs(batch: List[_Request]) -> int:
    return sum(request.pairs for request in batch)


def _carries_background(batch: List[_Request]) -> bool:
    """True when this physical batch holds any deferrable request."""
    return any(request.scheduling_class == CLASS_BACKGROUND for request in batch)


def _resolve(waiter: "asyncio.Future[None]") -> None:
    if not waiter.done():
        waiter.set_result(None)


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
            future.set_result(list(result or []))
    except Exception:
        # Already cancelled or settled by its caller. Nothing leaks: a settled
        # future is a terminal state.
        pass


def create_rerank_scheduler(
    predict: Callable[[List[Tuple[str, str]]], List[float]],
    config: object,
    logger: Optional[ServiceLogger] = None,
) -> RerankScheduler:
    """Build the one process-level rerank scheduler from service config."""
    workers = max(1, int(getattr(config, "reranker_inference_workers", 2)))
    return RerankScheduler(
        predict,
        service=str(getattr(config, "service_name", "rag")),
        max_batch_pairs=max(1, int(getattr(config, "reranker_max_batch_pairs", 64))),
        microbatch_window_ms=max(
            0.0, float(getattr(config, "reranker_microbatch_window_ms", 5.0))
        ),
        max_pending_pairs=max(
            1, int(getattr(config, "reranker_max_pending_pairs", 512))
        ),
        admission_timeout_seconds=max(
            0.001, float(getattr(config, "reranker_admission_timeout_seconds", 1.0))
        ),
        inference_workers=workers,
        max_background_inflight=max(
            1,
            min(
                workers,
                int(
                    getattr(
                        config,
                        "reranker_max_background_inflight",
                        max(1, workers - 1),
                    )
                ),
            ),
        ),
        logger=logger,
    )
