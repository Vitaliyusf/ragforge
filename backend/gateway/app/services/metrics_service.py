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
    EVAL_END_TO_END_TOKENS_PER_ITEM,
    MODEL_COST_PER_1K_TOKENS,
    FileAction,
    MetricsWindow,
    RagAction,
    VectorDbAction,
)
from app.core.errors import GatewayError, NotFoundError, ValidationError
from app.core.logging_config import ServiceLogger
from app.core.config import GatewayConfig
from app.core.rabbitmq_client import RabbitMQClient
from app.services import promql
from app.services.base import BaseRPCService
from app.services.prometheus_client import PrometheusClient, PrometheusUnavailable

TOKENS_PER_COST_UNIT = 1_000

# Prometheus data is never tenant-scoped here — see the module docstring.
PROMETHEUS_SCOPE = "all_tenants"

# Refusal kinds the rag eval handler reports, and the HTTP status each earns.
# 403 is raised as a GatewayError with an explicit status because the
# gateway's errors module does not re-export AuthorizationError.
EVAL_FORBIDDEN_STATUS = 403


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
                "retrieval_filtered_rate",
                "retrieval_filtered_by_reason",
                "reranker_p95",
                "reranker_top_score_buckets",
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
            "retrieval_filtered_rate": _scalar(metrics.get("retrieval_filtered_rate")),
            "retrieval_filtered_by_reason": _by_label(
                metrics.get("retrieval_filtered_by_reason"), "reason"
            ),
            "reranker_p95_seconds": _scalar(metrics.get("reranker_p95")),
            # Scored 0-10 by the reranker model, not 0-1 like the judge scores.
            "reranker_top_score_histogram": _histogram_from_le(
                metrics.get("reranker_top_score_buckets")
            ),
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
        vectors = await self._vector_metrics()
        metrics, available = await self._gather(
            [
                "ingestion_stage_rate",
                "file_processing_p95",
                "embedding_p95",
                "embedding_chunk_rate",
                "llm_p95",
                "llm_token_rate",
                "vector_search_rate",
                "kafka_consumer_lag",
                "dlq_rate",
                "vector_upsert_increase",
            ],
            window,
        )
        data: Dict[str, Any] = {
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
            "kafka_consumer_lag": _by_labels(
                metrics.get("kafka_consumer_lag"), ("topic", "group")
            ),
            "dlq_rate": _by_labels(metrics.get("dlq_rate"), ("service", "error_type")),
            # Counts are collection-wide, not tenant-scoped — `scope` says so
            # and the panel must repeat it. Growth is what the window added.
            "vectors": {
                **vectors,
                "growth": _by_label(metrics.get("vector_upsert_increase"), "collection"),
            },
        }
        return self._envelope(window, rag or files, available, data)

    # ------------------------------------------------------------------
    # Eval harness
    # ------------------------------------------------------------------

    async def list_eval_datasets(self) -> Dict[str, Any]:
        """List the tenant's golden-set datasets with counts and last-run times."""
        return await self._eval(RagAction.LIST_EVAL_DATASETS, {})

    async def create_eval_dataset(
        self,
        name: str,
        description: Optional[str],
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Store one uploaded dataset, or refuse it with a reason."""
        return await self._eval(
            RagAction.CREATE_EVAL_DATASET,
            {"name": name, "description": description, "items": items},
        )

    async def update_eval_dataset(
        self,
        dataset_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Rename a dataset or replace its items wholesale."""
        return await self._eval(
            RagAction.UPDATE_EVAL_DATASET,
            {
                "dataset_id": dataset_id,
                "name": name,
                "description": description,
                "items": items,
            },
        )

    async def delete_eval_dataset(self, dataset_id: str) -> Dict[str, Any]:
        """Delete one dataset. Its past runs are deliberately kept."""
        return await self._eval(
            RagAction.DELETE_EVAL_DATASET, {"dataset_id": dataset_id}
        )

    async def start_eval_run(
        self,
        dataset_id: str,
        mode: str = "retrieval",
    ) -> Dict[str, Any]:
        """Start a run and return its ``run_id`` immediately.

        Uses the short timeout on purpose: rag opens the run document and
        returns, executing it in the background, so this call is fast even
        for a 200-item dataset. The client polls :meth:`get_eval_run`.

        Args:
            dataset_id: The dataset to run.
            mode: ``retrieval`` (default, LLM-free and free of charge) or
                ``end_to_end``, which generates and judges an answer per
                item. rag validates the value again on arrival.
        """
        return await self._eval(
            RagAction.START_EVAL_RUN, {"dataset_id": dataset_id, "mode": mode}
        )

    @staticmethod
    def estimate_eval_cost(item_count: int, mode: str, model: str) -> Dict[str, Any]:
        """Estimate what one eval run will spend, for the pre-run warning.

        A ``retrieval`` run costs nothing — it never calls a model — and is
        reported as exactly that rather than as a small number.

        The token figures are coarse per-item averages from
        ``EVAL_END_TO_END_TOKENS_PER_ITEM``, not a measurement, and
        ``model_priced`` is False whenever the model is missing from
        ``MODEL_COST_PER_1K_TOKENS``. A $0.00 estimate with
        ``model_priced: False`` means "this model has no configured price",
        not "this run is free"; the UI must say which it is showing.
        """
        if mode != "end_to_end":
            return {
                "mode": mode,
                "item_count": item_count,
                "calls_per_item": 0,
                "estimated_tokens_in": 0,
                "estimated_tokens_out": 0,
                "estimated_cost_usd": 0.0,
                "model": None,
                "model_priced": True,
            }
        tokens_in, tokens_out = EVAL_END_TO_END_TOKENS_PER_ITEM
        total_in = tokens_in * item_count
        total_out = tokens_out * item_count
        price = MODEL_COST_PER_1K_TOKENS.get(model or "")
        priced = price is not None
        if price is None:
            price = DEFAULT_MODEL_COST_PER_1K_TOKENS
        return {
            "mode": mode,
            "item_count": item_count,
            # One generation call and one judge call per item.
            "calls_per_item": 2,
            "estimated_tokens_in": total_in,
            "estimated_tokens_out": total_out,
            "estimated_cost_usd": (total_in * price[0] + total_out * price[1])
            / TOKENS_PER_COST_UNIT,
            "model": model or None,
            "model_priced": priced,
        }

    async def list_eval_runs(
        self,
        dataset_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """List runs newest first, without their per-item rows."""
        return await self._eval(
            RagAction.LIST_EVAL_RUNS, {"dataset_id": dataset_id, "limit": limit}
        )

    async def get_eval_run(self, run_id: str) -> Dict[str, Any]:
        """Fetch one run, including its per-item drill-down rows."""
        return await self._eval(RagAction.GET_EVAL_RUN, {"run_id": run_id})

    async def _eval(self, action: RagAction, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send one eval action to rag and translate a typed refusal.

        rag reports refusals inside a successful reply under ``eval_error``
        rather than through the shared error envelope, which would flatten
        every failure into one generic 500 with no reason — see
        ``eval_runner._error_reply``. Translating them here is what lets a
        malformed upload come back as a 400 naming the offending item.
        """
        reply = await self._send(
            self.config.request_topics["rag"], {"action": action, **payload}
        )
        failure = (reply or {}).get("eval_error")
        if not failure:
            return reply
        message = failure.get("message") or "Eval request failed"
        kind = failure.get("kind")
        if kind == "validation":
            raise ValidationError(message)
        if kind == "not_found":
            raise NotFoundError(message)
        raise GatewayError(message, status_code=EVAL_FORBIDDEN_STATUS)

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

    async def _vector_metrics(self) -> Dict[str, Any]:
        """Fetch collection point counts from the vector_db service.

        Returns an empty dict rather than raising. Vector counts are one card
        on the pipeline panel; a vector_db outage should cost that card, not
        the funnel, the stuck-file list and the cost breakdown beside it.
        """
        routing_key = self.config.request_topics.get("vector_db")
        if not routing_key:
            return {}
        try:
            return await self._send(routing_key, {"action": VectorDbAction.GET_METRICS})
        except Exception as exc:
            self.logger.log(
                "metrics_service:vector_metrics",
                "vector_db metrics unavailable; omitting collection counts",
                {"error": str(exc)},
            )
            return {}

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

            ``by_tenant`` carries the same rows rag sent, priced only when
            there is exactly one — see the loop for why.
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
        by_tenant: List[Dict[str, Any]] = []
        tenant_rows = cost.get("by_tenant") or []
        for entry in tenant_rows:
            # `by_tenant` and `by_model` aggregate the same turns, so with the
            # single row rag can return, that tenant's spend *is* the window
            # total. More than one row would need a per-tenant model split rag
            # does not send, so the cost is left None rather than apportioned
            # by a guess.
            by_tenant.append(
                {**entry, "estimated_cost_usd": total if len(tenant_rows) == 1 else None}
            )
        return {
            "by_model": by_model,
            "by_tenant": by_tenant,
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


def _histogram_from_le(result: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Convert cumulative ``le`` bucket counts into discrete ``{bucket, count}``.

    A Prometheus ``_bucket`` series is cumulative: ``le="2"`` counts everything
    at or below 2, not the 1-to-2 band. Handing those numbers to a bar chart
    draws a staircase that only ever rises, which reads as a distribution and
    is not one — so each bucket has its predecessor subtracted here.

    ``+Inf`` is folded into the final labelled bucket rather than shown: it is
    an artefact of the bucket definition, not a score range an operator can act
    on. A negative difference (a counter reset mid-window) is clamped to 0.

    Returns:
        Buckets in ascending order, labelled by their upper bound. Empty when
        the query matched nothing, which the chart renders as no chart at all
        rather than as a row of zeroes.
    """
    if not result:
        return []
    edges: List[Tuple[float, float]] = []
    infinite = 0.0
    for entry in result:
        raw = (entry.get("metric") or {}).get("le")
        value = _number((entry.get("value") or [None, None])[1])
        if raw is None or value is None:
            continue
        try:
            bound = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isinf(bound):
            infinite = value
            continue
        edges.append((bound, value))

    if not edges:
        return []
    edges.sort(key=lambda item: item[0])

    buckets: List[Dict[str, Any]] = []
    previous = 0.0
    for bound, cumulative in edges:
        buckets.append({"bucket": _bucket_label(bound), "count": max(0.0, cumulative - previous)})
        previous = cumulative
    # Anything above the last finite edge belongs to that edge's band; the
    # +Inf series is the same running total, so the overflow is its remainder.
    if infinite > previous:
        buckets[-1]["count"] += infinite - previous
    return buckets


def _bucket_label(bound: float) -> str:
    """Label one histogram bucket by its upper bound, without a trailing .0."""
    return str(int(bound)) if float(bound).is_integer() else str(bound)


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
