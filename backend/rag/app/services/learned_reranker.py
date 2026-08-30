"""Bounded cross-encoder reranking with deterministic degradation."""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from shared.metrics import METRICS


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
    """Run one learned model off the event loop and bound overload behavior."""

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
        self.batch_size = max(1, int(getattr(config, "reranker_batch_size", 8)))
        self.max_length = max(32, int(getattr(config, "reranker_max_length", 512)))
        self._model_factory = model_factory or _default_model_factory
        self._model: Any = None
        self._model_error: Optional[BaseException] = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reranker")
        self._inflight: Optional[Future[List[float]]] = None
        self._state_lock = asyncio.Lock()

    @property
    def model_ref(self) -> str:
        return f"{self.model_name}@{self.model_revision}"

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._model_error is not None:
            raise RuntimeError(
                "reranker model initialization previously failed"
            ) from self._model_error
        try:
            self._model = self._model_factory(
                self.model_name,
                self.model_revision,
                self.max_length,
            )
        except BaseException as exc:
            self._model_error = exc
            raise
        return self._model

    def _predict(self, query: str, passages: Sequence[str]) -> List[float]:
        model = self._load_model()
        values = model.predict(
            [(query, passage) for passage in passages],
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
        if len(scores) != len(passages):
            raise RuntimeError(
                "reranker returned a different number of scores than passages"
            )
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
            service="rag", status=status, traffic_class=traffic_class
        ).inc()
        METRICS.reranker_duration.labels(
            service="rag", status=status, traffic_class=traffic_class
        ).observe(elapsed)
        METRICS.reranker_candidate_count.labels(
            service="rag", traffic_class=traffic_class
        ).observe(candidate_count)
        if top_score is not None:
            METRICS.reranker_top_score.labels(
                service="rag", traffic_class=traffic_class
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

        async with self._state_lock:
            if self._inflight is not None and not self._inflight.done():
                status = "busy"
                elapsed = time.monotonic() - started
                self._observe(
                    status=status,
                    elapsed=elapsed,
                    candidate_count=len(bounded),
                    traffic_class=traffic_class,
                )
                return RerankResult(bounded, status, elapsed * 1000, len(bounded))
            self._inflight = self._executor.submit(self._predict, query, passages)
            future = self._inflight

        status = "success"
        try:
            scores = await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(future)),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            status = "timeout"
            scores = []
        except Exception:
            status = "error"
            scores = []
        finally:
            if future.done():
                async with self._state_lock:
                    if self._inflight is future:
                        self._inflight = None

        elapsed = time.monotonic() - started
        if status != "success":
            self._observe(
                status=status,
                elapsed=elapsed,
                candidate_count=len(bounded),
                traffic_class=traffic_class,
            )
            return RerankResult(bounded, status, elapsed * 1000, len(bounded))

        ranked: List[tuple[int, Dict[str, Any]]] = []
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
