"""Admin metrics facade — fans out to rag and files, merges in Prometheus.

Each route calls exactly one method here, and that method issues at most one
RPC per downstream service plus one concurrent batch of Prometheus queries.

Two rules shape everything below:

- **Prometheus may be dead.** Every Prometheus read goes through
  :meth:`_gather`, which converts an outage into ``prometheus_available:
  False`` and simply omits those fields. A monitoring outage degrades panels;
  it never produces a 5xx.
- **Prometheus numbers are platform-wide.** The phase-1 series carry no
  tenant label, so every response says so via ``prometheus_scope``. The
  tenant-scoped figures are the MongoDB-backed ones from rag and files.
"""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.core.constants import (
    DEFAULT_MODEL_COST_PER_1K_TOKENS,
    MODEL_COST_PER_1K_TOKENS,
    FileAction,
    MetricsWindow,
    RagAction,
)
from app.core.logging_config import ServiceLogger
from app.core.config import GatewayConfig
from app.core.rabbitmq_client import RabbitMQClient
from app.services import promql
from app.services.base import BaseRPCService
from app.services.prometheus_client import PrometheusClient, PrometheusUnavailable

TOKENS_PER_COST_UNIT = 1_000

# Prometheus data is never tenant-scoped here — see the module docstring.
PROMETHEUS_SCOPE = "all_tenants"


class MetricsService(BaseRPCService):
    """Assemble one admin metrics response per route."""

    def __init__(
        self,
        rpc_client: RabbitMQClient,
        logger: ServiceLogger,
        config: GatewayConfig,
        prometheus: PrometheusClient,
    ) -> None:
        super().__init__(rpc_client, logger, config)
        self.prometheus = prometheus

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    async def overview(
        self,
        window: MetricsWindow,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the KPI header: latency, throughput, quality, and spend."""
        rag = await self._rag_sections(["overview", "cost"], window, tenant_id)
        metrics, available = await self._gather(
            [
                "turn_latency_p50",
                "turn_latency_p95",
                "turn_latency_p99",
                "ttft_p95",
                "qps",
                "error_rate",
            ],
            window,
        )
        data = {
            **_without_tenant(rag.get("overview") or {}),
            "cost": self._priced(rag.get("cost") or {}),
            "turn_latency_seconds": {
                "p50": _by_label(metrics.get("turn_latency_p50"), "answer_mode"),
                "p95": _by_label(metrics.get("turn_latency_p95"), "answer_mode"),
                "p99": _by_label(metrics.get("turn_latency_p99"), "answer_mode"),
            },
            "ttft_p95_seconds": _by_label(metrics.get("ttft_p95"), "answer_mode"),
            "qps": _scalar(metrics.get("qps")),
            "prometheus_error_rate": _scalar(metrics.get("error_rate")),
        }
        return self._envelope(window, rag, available, data)

    async def latency(
        self,
        window: MetricsWindow,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build latency time series, stage breakdown, and transport timings."""
        rag = await self._rag_sections(["overview"], window, tenant_id)
        metrics, available = await self._gather(
            [
                "turn_latency_p50",
                "turn_latency_p95",
                "turn_latency_p99",
                "ttft_p50",
                "ttft_p95",
                "ttft_p99",
                "stage_p95",
                "http_p95",
                "http_p99",
                "http_request_rate",
                "rpc_roundtrip_p95",
            ],
            window,
        )
        series, series_available = await self._gather_range(
            ["turn_latency_p95_series", "ttft_p95_series", "qps_series"],
            window,
        )
        data = {
            **_without_tenant(rag.get("overview") or {}),
            "turn_latency_seconds": {
                "p50": _by_label(metrics.get("turn_latency_p50"), "answer_mode"),
                "p95": _by_label(metrics.get("turn_latency_p95"), "answer_mode"),
                "p99": _by_label(metrics.get("turn_latency_p99"), "answer_mode"),
            },
            "ttft_seconds": {
                "p50": _by_label(metrics.get("ttft_p50"), "answer_mode"),
                "p95": _by_label(metrics.get("ttft_p95"), "answer_mode"),
                "p99": _by_label(metrics.get("ttft_p99"), "answer_mode"),
            },
            "stage_p95_seconds": _by_label(metrics.get("stage_p95"), "stage"),
            "http_p95_seconds": _by_label(metrics.get("http_p95"), "service"),
            "http_p99_seconds": _by_label(metrics.get("http_p99"), "service"),
            "http_request_rate": _by_label(metrics.get("http_request_rate"), "service"),
            "rpc_roundtrip_p95_seconds": _by_label(
                metrics.get("rpc_roundtrip_p95"), "downstream"
            ),
            "series": {key: _series(value) for key, value in series.items()},
        }
        return self._envelope(window, rag, available and series_available, data)

    async def retrieval(
        self,
        window: MetricsWindow,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build retrieval quality: hit rate, scores, chunks, reranker lift."""
        rag = await self._rag_sections(["retrieval"], window, tenant_id)
        metrics, available = await self._gather(
            [
                "vector_search_p95",
                "vector_search_rate",
                "retrieval_score_p50",
                "sources_per_query_p95",
            ],
            window,
        )
        data = {
            **_without_tenant(rag.get("retrieval") or {}),
            "vector_search_p95_seconds": _by_label(
                metrics.get("vector_search_p95"), "collection"
            ),
            "vector_search_rate": _by_label(
                metrics.get("vector_search_rate"), "collection"
            ),
            "retrieval_score_p50": _scalar(metrics.get("retrieval_score_p50")),
            "sources_per_query_p95": _scalar(metrics.get("sources_per_query_p95")),
        }
        return self._envelope(window, rag, available, data)

    async def quality(
        self,
        window: MetricsWindow,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build answer quality: distributions, proxy hallucination, worst turns.

        Entirely MongoDB-backed. Prometheus holds no per-turn judge scores, so
        this route reports ``prometheus_available`` from a health check only,
        rather than pretending a query contributed to it.
        """
        rag = await self._rag_sections(["quality", "worst_turns"], window, tenant_id)
        available = await self.prometheus.is_available()
        data = {
            **_without_tenant(rag.get("quality") or {}),
            "worst_turns": rag.get("worst_turns") or [],
        }
        return self._envelope(window, rag, available, data)

    async def pipeline(
        self,
        window: MetricsWindow,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the ingestion funnel, throughput, and token/cost breakdown."""
        rag = await self._rag_sections(["cost"], window, tenant_id)
        files = await self._files_metrics(window, tenant_id)
        metrics, available = await self._gather(
            [
                "ingestion_stage_rate",
                "file_processing_p95",
                "embedding_p95",
                "embedding_chunk_rate",
                "llm_p95",
                "llm_token_rate",
                "vector_search_rate",
            ],
            window,
        )
        data = {
            "ingestion": _without_tenant(files),
            "cost": self._priced(rag.get("cost") or {}),
            "ingestion_stage_rate": _by_labels(
                metrics.get("ingestion_stage_rate"), ("stage", "outcome")
            ),
            # Per-stage duration exists only here: the files database records
            # stage state, never elapsed time.
            "file_processing_p95_seconds": _by_label(
                metrics.get("file_processing_p95"), "stage"
            ),
            "embedding_p95_seconds": _scalar(metrics.get("embedding_p95")),
            "embedding_chunk_rate": _scalar(metrics.get("embedding_chunk_rate")),
            "llm_p95_seconds": _by_label(metrics.get("llm_p95"), "model"),
            "llm_token_rate": _by_labels(
                metrics.get("llm_token_rate"), ("model", "direction")
            ),
            "vector_search_rate": _by_label(
                metrics.get("vector_search_rate"), "collection"
            ),
        }
        return self._envelope(window, rag or files, available, data)

    # ------------------------------------------------------------------
    # Downstream RPC
    # ------------------------------------------------------------------

    async def _rag_sections(
        self,
        sections: List[str],
        window: MetricsWindow,
        tenant_id: Optional[str],
    ) -> Dict[str, Any]:
        """Fetch several rag metric sections in one RPC round-trip."""
        return await self._send(
            self.config.request_topics["rag"],
            {
                "action": RagAction.GET_METRICS,
                "sections": sections,
                "window": window.value,
                "tenant_id": tenant_id,
            },
        )

    async def _files_metrics(
        self,
        window: MetricsWindow,
        tenant_id: Optional[str],
    ) -> Dict[str, Any]:
        """Fetch the ingestion funnel, durations, and stuck files."""
        return await self._send(
            self.config.request_topics["files"],
            {
                "action": FileAction.GET_METRICS,
                "window": window.value,
                "tenant_id": tenant_id,
            },
        )

    # ------------------------------------------------------------------
    # Prometheus
    # ------------------------------------------------------------------

    async def _gather(
        self,
        keys: Iterable[str],
        window: MetricsWindow,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], bool]:
        """Run several instant queries concurrently.

        Concurrency is what keeps a hung Prometheus cheap: sequentially, ten
        queries against an unresponsive server would cost ten timeouts, while
        together they cost one.

        Returns:
            The results by key, and whether every query succeeded. On any
            failure the flag is False and the failed keys are simply absent,
            so callers render the fields they do have.
        """
        names = list(keys)
        if not names:
            return {}, True
        results = await asyncio.gather(
            *(self.prometheus.query(promql.render(name, window)) for name in names),
            return_exceptions=True,
        )
        return self._collect(names, results)

    async def _gather_range(
        self,
        keys: Iterable[str],
        window: MetricsWindow,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], bool]:
        """Run several range queries concurrently over the window."""
        names = list(keys)
        if not names:
            return {}, True
        end = datetime.now(timezone.utc).timestamp()
        start = end - promql.window_seconds(window)
        step = promql.range_step(window)
        results = await asyncio.gather(
            *(
                self.prometheus.query_range(
                    promql.render(name, window, range_query=True), start, end, step
                )
                for name in names
            ),
            return_exceptions=True,
        )
        return self._collect(names, results)

    def _collect(
        self,
        names: List[str],
        results: List[Any],
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], bool]:
        """Split gathered results into successes and an availability flag."""
        collected: Dict[str, List[Dict[str, Any]]] = {}
        available = True
        for name, result in zip(names, results):
            if isinstance(result, PrometheusUnavailable):
                available = False
                continue
            if isinstance(result, BaseException):
                raise result
            collected[name] = result
        if not available:
            self.logger.log(
                "metrics_service:prometheus",
                "Prometheus unavailable; serving MongoDB-backed metrics only",
                {"queries": names},
            )
        return collected, available

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _priced(cost: Dict[str, Any]) -> Dict[str, Any]:
        """Apply the gateway cost table to rag's token sums.

        The rag service returns tokens and no price. Pricing lives only in
        ``MODEL_COST_PER_1K_TOKENS``, so there is one table to maintain.

        Returns:
            The cost section with ``estimated_cost_usd`` per model and in
            total, plus ``models_without_pricing`` naming every model that
            fell back to the default. A $0.00 total next to a non-empty
            ``models_without_pricing`` means "nothing here is priced", not
            "this was free".
        """
        by_model: List[Dict[str, Any]] = []
        unpriced: List[str] = []
        total = 0.0
        for entry in cost.get("by_model") or []:
            model = entry.get("model")
            price = MODEL_COST_PER_1K_TOKENS.get(model or "")
            if price is None:
                price = DEFAULT_MODEL_COST_PER_1K_TOKENS
                unpriced.append(model)
            estimated = (
                entry.get("tokens_in", 0) * price[0]
                + entry.get("tokens_out", 0) * price[1]
            ) / TOKENS_PER_COST_UNIT
            total += estimated
            by_model.append({**entry, "estimated_cost_usd": estimated})
        return {
            "by_model": by_model,
            "tokens_in": cost.get("tokens_in", 0),
            "tokens_out": cost.get("tokens_out", 0),
            "estimated_cost_usd": total,
            "models_without_pricing": unpriced,
        }

    @staticmethod
    def _envelope(
        window: MetricsWindow,
        downstream: Dict[str, Any],
        prometheus_available: bool,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Wrap one route's data in the shared metrics response contract.

        ``tenant_id`` is echoed from the downstream reply — the tenant whose
        documents were actually aggregated — rather than from the request, so
        the response can never name a tenant it did not read.
        """
        return {
            "window": window.value,
            "tenant_id": downstream.get("tenant_id"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "prometheus_available": prometheus_available,
            "prometheus_scope": PROMETHEUS_SCOPE,
            "data": data,
        }


# ---------------------------------------------------------------------------
# Prometheus result parsing
# ---------------------------------------------------------------------------

def _number(raw: Any) -> Optional[float]:
    """Parse one Prometheus sample value into a JSON-safe float.

    Prometheus reports absent or undefined results as ``NaN``/``Inf``, and
    ``json.dumps`` renders those as bare ``NaN``/``Infinity`` tokens, which
    are not valid JSON and break strict parsers. They become ``null``.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) or math.isinf(value) else value


def _scalar(result: Optional[List[Dict[str, Any]]]) -> Optional[float]:
    """Return the single value of a scalar instant query, or None."""
    if not result:
        return None
    return _number((result[0].get("value") or [None, None])[1])


def _by_label(
    result: Optional[List[Dict[str, Any]]],
    label: str,
) -> Dict[str, Optional[float]]:
    """Index an instant query's results by one label value."""
    if not result:
        return {}
    return {
        str((entry.get("metric") or {}).get(label, "")): _number(
            (entry.get("value") or [None, None])[1]
        )
        for entry in result
    }


def _by_labels(
    result: Optional[List[Dict[str, Any]]],
    labels: Tuple[str, ...],
) -> List[Dict[str, Any]]:
    """Flatten an instant query's results, keeping several labels each.

    A list rather than a nested dict: two labels would otherwise need a
    composite key, and a composite key is a string nobody can filter on.
    """
    if not result:
        return []
    rows = []
    for entry in result:
        metric = entry.get("metric") or {}
        row: Dict[str, Any] = {label: metric.get(label) for label in labels}
        row["value"] = _number((entry.get("value") or [None, None])[1])
        rows.append(row)
    return rows


def _series(result: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Flatten a range query's first series into ``{t, v}`` points."""
    if not result:
        return []
    values = result[0].get("values") or []
    return [
        {"t": point[0], "v": _number(point[1])}
        for point in values
        if isinstance(point, (list, tuple)) and len(point) == 2
    ]


def _without_tenant(section: Dict[str, Any]) -> Dict[str, Any]:
    """Drop the downstream tenant echo from a section body.

    The tenant belongs in the envelope, not repeated inside every panel.
    """
    return {key: value for key, value in section.items() if key != "tenant_id"}
