"""Bounded cross-encoder reranking with deterministic degradation."""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.services.rerank_scheduler import (
    RerankScheduler,
    RerankSchedulerOverloaded,
    create_rerank_scheduler,
    scheduling_class_for,
)
from shared.metrics import METRICS, RERANKER_STATUSES


RERANKER_IMPLEMENTATION = "sentence_transformers_cross_encoder"
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_RERANKER_REVISION = "b5160aeac3c6c8fe7beaaaf04c9e0142826b58d1"


@dataclass(frozen=True)
class RerankResult:
    """The ranked candidates and the explicit outcome of model inference."""

    candidates: List[Dict[str, Any]]
    status: str
    latency_ms: float
    candidate_count: int


def _text(candidate: Dict[str, Any]) -> str:
    payload = candidate.get("payload") or {}
    metadata = candidate.get("metadata") or payload.get("metadata") or {}
    return str(
        candidate.get("text")
        or candidate.get("chunk")
        or candidate.get("content")
        or payload.get("text")
        or metadata.get("text")
        or ""
    )


def _default_model_factory(model_name: str, revision: str, max_length: int) -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder(
        model_name,
        revision=revision,
        max_length=max_length,
        local_files_only=True,
    )


class CrossEncoderReranker:
    """Own one learned model and score through one bounded scheduler.

    The model instance, its pinned revision and its ``batch_size`` /
    ``max_length`` contract live here. *When* a pair is scored — which forward
    pass carries it, and behind how much other work — belongs to
    :class:`~app.services.rerank_scheduler.RerankScheduler`.

    Before CONC-05 those two were the same decision: a single-flight executor
    meant a request arriving while another was reranking got ``busy`` and its
    pipeline fell back to the RRF ordering, so concurrency alone could change
    the final ranking. Now contention queues instead, and ``busy`` is reserved
    for real overload — the bounded queue refusing work before its deadline.
    """

    def __init__(
        self,
        config: Any,
        *,
        model_factory: Optional[Callable[[str, str, int], Any]] = None,
    ) -> None:
        self.enabled = bool(getattr(config, "reranker_enabled", False))
        self.model_name = str(
            getattr(config, "reranker_model", DEFAULT_RERANKER_MODEL)
            or DEFAULT_RERANKER_MODEL
        )
        self.model_revision = str(
            getattr(config, "reranker_model_revision", DEFAULT_RERANKER_REVISION)
            or DEFAULT_RERANKER_REVISION
        )
        self.candidate_limit = max(1, int(getattr(config, "reranker_candidate_k", 20)))
        self.timeout_seconds = max(
            0.001, float(getattr(config, "reranker_timeout_seconds", 5.0))
        )
        # Backpressure is bounded separately from inference: a request that
        # cannot even be *queued* within this should be told so quickly, not
        # left to burn its whole `reranker_timeout_seconds` in a queue.
        self.admission_timeout_seconds = max(
            0.001, float(getattr(config, "reranker_admission_timeout_seconds", 1.0))
        )
        self.batch_size = max(1, int(getattr(config, "reranker_batch_size", 8)))
        self.max_length = max(32, int(getattr(config, "reranker_max_length", 512)))
        self.service = str(getattr(config, "service_name", "rag"))
        self._model_factory = model_factory or _default_model_factory
        self._model: Any = None
        self._model_error: Optional[BaseException] = None
        # Guards model construction. `_load_model` runs on scheduler worker
        # threads, and without this two workers racing the first rerank would
        # each build a CrossEncoder — two copies of the model in memory.
        self._model_lock = threading.Lock()
        self._scheduler: RerankScheduler = create_rerank_scheduler(self._predict, config)

    @property
    def model_ref(self) -> str:
        return f"{self.model_name}@{self.model_revision}"

    @property
    def scheduler(self) -> RerankScheduler:
        """The one process-level scheduler behind this model."""
        return self._scheduler

    def shutdown(self, *, drain: bool = True, timeout: float = 10.0) -> bool:
        """Stop admission and settle every outstanding rerank request."""
        return self._scheduler.shutdown(drain=drain, timeout=timeout)

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model
            if self._model_error is not None:
                raise RuntimeError(
                    "reranker model initialization previously failed"
                ) from self._model_error
            try:
                model = self._model_factory(
                    self.model_name,
                    self.model_revision,
                    self.max_length,
                )
            except BaseException as exc:
                self._model_error = exc
                METRICS.model_loads_total.labels(
                    service=self.service, model_kind="reranker", outcome="failure"
                ).inc()
                raise
            self._model = model
            METRICS.model_loads_total.labels(
                service=self.service, model_kind="reranker", outcome="success"
            ).inc()
            return self._model

    def _predict(self, pairs: List[Tuple[str, str]]) -> List[float]:
        """Score one physical batch of ``(query, passage)`` pairs.

        Called only on a scheduler worker thread. ``batch_size`` is still the
        model's own internal chunk size — the scheduler decides how many pairs
        arrive here, not how many the model tokenizes at once — so a pair is
        scored exactly as it was before CONC-05.
        """
        model = self._load_model()
        values = model.predict(
            list(pairs),
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        if hasattr(values, "tolist"):
            values = values.tolist()
        if not isinstance(values, list):
            values = [values]
        scores: List[float] = []
        for value in values:
            if isinstance(value, list):
                value = value[-1]
            scores.append(float(value))
        return scores

    def _observe(
        self,
        *,
        status: str,
        elapsed: float,
        candidate_count: int,
        traffic_class: str,
        top_score: Optional[float] = None,
    ) -> None:
        METRICS.reranker_requests_total.labels(
            service=self.service, status=status, traffic_class=traffic_class
        ).inc()
        METRICS.reranker_duration.labels(
            service=self.service, status=status, traffic_class=traffic_class
        ).observe(elapsed)
        METRICS.reranker_candidate_count.labels(
            service=self.service, traffic_class=traffic_class
        ).observe(candidate_count)
        # The CONC-00 terminal-status counter carries only the four closed
        # values; `disabled` and `insufficient_input` are pipeline shapes, not
        # inference outcomes, and would widen a label space the track pins.
        if status in RERANKER_STATUSES:
            METRICS.reranker_status_total.labels(
                service=self.service, status=status
            ).inc()
        if top_score is not None:
            METRICS.reranker_top_score.labels(
                service=self.service, traffic_class=traffic_class
            ).observe(top_score)

    async def rerank(
        self,
        query: str,
        candidates: Sequence[Dict[str, Any]],
        *,
        traffic_class: str = "live",
    ) -> RerankResult:
        """Rerank at most ``candidate_limit`` items; preserve input order on fallback."""
        bounded = [dict(candidate) for candidate in candidates[: self.candidate_limit]]
        started = time.monotonic()
        if not self.enabled:
            return RerankResult(bounded, "disabled", 0.0, len(bounded))
        passages = [_text(candidate) for candidate in bounded]
        if len(bounded) < 2 or not query or any(not passage for passage in passages):
            status = "insufficient_input"
            elapsed = time.monotonic() - started
            self._observe(
                status=status,
                elapsed=elapsed,
                candidate_count=len(bounded),
                traffic_class=traffic_class,
            )
            return RerankResult(bounded, status, elapsed * 1000, len(bounded))

        scheduling_class = scheduling_class_for(traffic_class)
        deadline = started + self.timeout_seconds
        self._scheduler.start()

        status = "success"
        scores: List[float] = []
        try:
            # Admission is bounded by its own knob *and* by the caller's
            # deadline: the pipeline promised an answer within
            # `reranker_timeout_seconds`, so queueing can never extend that
            # promise, and a saturated queue gives up sooner still.
            future = await self._scheduler.submit(
                query,
                passages,
                scheduling_class=scheduling_class,
                admission_timeout=max(
                    0.0,
                    min(
                        self.admission_timeout_seconds,
                        deadline - time.monotonic(),
                    ),
                ),
            )
        except RerankSchedulerOverloaded:
            status = "busy"
        else:
            awaitable = asyncio.wrap_future(future)
            try:
                scores = await asyncio.wait_for(
                    awaitable, timeout=max(0.0, deadline - time.monotonic())
                )
            except (asyncio.TimeoutError, TimeoutError):
                # `wait_for` already cancelled the wrapper, which cancels the
                # scheduler future. A request not yet composed into a batch is
                # dropped and its capacity released; one already running keeps
                # its slot, so no other request's score offsets can shift.
                future.cancel()
                self._record_inference_timeout(scheduling_class)
                status = "timeout"
            except Exception:
                status = "error"

        elapsed = time.monotonic() - started
        if status != "success" or len(scores) != len(bounded):
            if status == "success":
                # A count mismatch is never silently absorbed into a partial
                # ranking: this request fails explicitly and falls back.
                status = "error"
            self._observe(
                status=status,
                elapsed=elapsed,
                candidate_count=len(bounded),
                traffic_class=traffic_class,
            )
            return RerankResult(bounded, status, elapsed * 1000, len(bounded))

        ranked: List[Tuple[int, Dict[str, Any]]] = []
        for index, (candidate, score) in enumerate(zip(bounded, scores)):
            candidate["retrieval_score"] = candidate.get("score")
            candidate["reranker_score"] = score
            ranked.append((index, candidate))
        ranked.sort(key=lambda item: (-float(item[1]["reranker_score"]), item[0]))
        result = [candidate for _, candidate in ranked]
        self._observe(
            status=status,
            elapsed=elapsed,
            candidate_count=len(result),
            traffic_class=traffic_class,
            top_score=float(result[0]["reranker_score"]) if result else None,
        )
        return RerankResult(result, status, elapsed * 1000, len(result))

    def _record_inference_timeout(self, scheduling_class: str) -> None:
        METRICS.reranker_scheduler_timeouts_total.labels(
            service=self.service, rerank_class=scheduling_class, phase="inference"
        ).inc()
