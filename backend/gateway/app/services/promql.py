"""Every PromQL expression the metrics tab issues, in one place.

The tab needs roughly two dozen queries. Inline strings in route handlers
become unmaintainable immediately, so handlers name a key here instead.

Placeholders, substituted via :class:`string.Template`: ``${window}`` is the
rate window used for smoothing (minutes, even for a 30-day selection), and
``${range}`` is the selected window's full duration. Use ``${range}`` only for
``increase()``-style totals that must cover the whole period; every rate keeps
using ``${window}``.
PromQL is full of literal braces, so ``str.format`` would require escaping
every label matcher; ``$``-substitution has no such collision.

There is deliberately no ``${tenant}``. The phase-1 metrics in
``shared/metrics.py`` carry no tenant label — deliberately, since tenant is
unbounded cardinality — so no Prometheus number here can be scoped to one
tenant. Callers must present these as platform-wide; the tenant-scoped
numbers come from MongoDB via the rag and files services.
"""
from __future__ import annotations

from string import Template

from app.core.constants import MetricsWindow

# Prometheus returns NaN for 0/0 and an empty vector when the denominator
# series is absent. Clamping keeps a quiet window at 0.0 instead.
_EPSILON = "0.000000001"

_ERROR_RATE = (
    'sum(rate(ragapp_rag_queries_total{status="error"}[${window}])) '
    "/ clamp_min(sum(rate(ragapp_rag_queries_total[${window}])), " + _EPSILON + ")"
)

INSTANT_QUERIES: dict[str, str] = {
    # ── Turn latency, by answer mode ──────────────────────────────────
    "turn_latency_p50": "histogram_quantile(0.50, sum by (answer_mode, le) (rate(ragapp_rag_query_duration_seconds_bucket[${window}])))",
    "turn_latency_p95": "histogram_quantile(0.95, sum by (answer_mode, le) (rate(ragapp_rag_query_duration_seconds_bucket[${window}])))",
    "turn_latency_p99": "histogram_quantile(0.99, sum by (answer_mode, le) (rate(ragapp_rag_query_duration_seconds_bucket[${window}])))",

    # ── Time to first token ───────────────────────────────────────────
    "ttft_p50": "histogram_quantile(0.50, sum by (answer_mode, le) (rate(ragapp_rag_ttft_seconds_bucket[${window}])))",
    "ttft_p95": "histogram_quantile(0.95, sum by (answer_mode, le) (rate(ragapp_rag_ttft_seconds_bucket[${window}])))",
    "ttft_p99": "histogram_quantile(0.99, sum by (answer_mode, le) (rate(ragapp_rag_ttft_seconds_bucket[${window}])))",

    # ── Graph stages ──────────────────────────────────────────────────
    "stage_p95": "histogram_quantile(0.95, sum by (stage, le) (rate(ragapp_rag_stage_duration_seconds_bucket[${window}])))",

    # ── Per-service HTTP ──────────────────────────────────────────────
    # ragapp_request_duration_seconds is declared in shared/metrics.py but
    # never observed anywhere, so these read the instrumentator's real
    # series. The `service` label comes from the scrape target definitions
    # in docker/prometheus/prometheus.yml.
    "http_p95": 'histogram_quantile(0.95, sum by (service, le) (rate(http_request_duration_seconds_bucket{job="ragapp"}[${window}])))',
    "http_p99": 'histogram_quantile(0.99, sum by (service, le) (rate(http_request_duration_seconds_bucket{job="ragapp"}[${window}])))',
    "http_request_rate": 'sum by (service) (rate(http_requests_total{job="ragapp"}[${window}]))',

    # ── RPC ───────────────────────────────────────────────────────────
    "rpc_roundtrip_p95": "histogram_quantile(0.95, sum by (downstream, le) (rate(ragapp_rpc_roundtrip_seconds_bucket[${window}])))",

    # ── Throughput and errors ─────────────────────────────────────────
    "qps": "sum(rate(ragapp_rag_queries_total[${window}]))",
    "error_rate": _ERROR_RATE,

    # ── Resilience ────────────────────────────────────────────────────
    "circuit_breaker_state": "max by (service, downstream) (ragapp_circuit_breaker_state)",
    "rate_limiter_rejection_rate": "sum by (service) (rate(ragapp_rate_limiter_rejected_total[${window}]))",
    "dlq_rate": "sum by (service, error_type) (rate(ragapp_dlq_messages_total[${window}]))",

    # ── Retrieval ─────────────────────────────────────────────────────
    "vector_search_p95": "histogram_quantile(0.95, sum by (collection, le) (rate(ragapp_vector_search_duration_seconds_bucket[${window}])))",
    "vector_search_rate": "sum by (collection) (rate(ragapp_vector_searches_total[${window}]))",
    "retrieval_score_p50": "histogram_quantile(0.50, sum by (le) (rate(ragapp_rag_retrieval_score_bucket[${window}])))",
    "sources_per_query_p95": "histogram_quantile(0.95, sum by (le) (rate(ragapp_rag_sources_per_query_bucket[${window}])))",
    # Numerator and denominator are the pair recorded at the policy gate in
    # rag's _normalize_chunks, so this is a true fraction of judged chunks.
    "retrieval_filtered_rate": (
        "sum(rate(ragapp_rag_chunks_filtered_total[${window}])) "
        "/ clamp_min(sum(rate(ragapp_rag_chunks_considered_total[${window}])), "
        + _EPSILON
        + ")"
    ),
    "retrieval_filtered_by_reason": "sum by (reason) (rate(ragapp_rag_chunks_filtered_total[${window}]))",
    # Phase 1 records both of these; nothing queried them until now. The lift
    # number alone cannot answer "is the reranker earning its latency".
    "reranker_p95": "histogram_quantile(0.95, sum by (le) (rate(ragapp_reranker_duration_seconds_bucket[${window}])))",
    # Cumulative-by-`le` counts over the whole window; the gateway converts
    # them to discrete buckets before they reach the UI.
    "reranker_top_score_buckets": "sum by (le) (increase(ragapp_reranker_top_score_bucket[${range}]))",

    # ── Embedding and generation ──────────────────────────────────────
    "embedding_p95": "histogram_quantile(0.95, sum by (le) (rate(ragapp_embedding_duration_seconds_bucket[${window}])))",
    "embedding_chunk_rate": "sum(rate(ragapp_embedding_chunks_total[${window}]))",
    "llm_p95": "histogram_quantile(0.95, sum by (model, le) (rate(ragapp_llm_request_duration_seconds_bucket[${window}])))",
    "llm_token_rate": "sum by (model, direction) (rate(ragapp_llm_tokens_total[${window}]))",

    # ── Ingestion pipeline ────────────────────────────────────────────
    "ingestion_stage_rate": "sum by (stage, outcome) (rate(ragapp_ingestion_stage_total[${window}]))",
    "file_processing_p95": "histogram_quantile(0.95, sum by (stage, le) (rate(ragapp_file_processing_duration_seconds_bucket[${window}])))",
    # A gauge, so it is read at its current value rather than rated. Absent
    # series mean no consumer has fetched yet — not a lag of zero.
    "kafka_consumer_lag": "max by (topic, group) (ragapp_kafka_consumer_lag)",
    # Vectors added over the selected window — hence ${range}, not ${window}.
    # `increase` over a counter, so a vector_db restart does not read as a
    # sudden negative.
    "vector_upsert_increase": "sum by (collection) (increase(ragapp_vector_upserts_total[${range}]))",
}

RANGE_QUERIES: dict[str, str] = {
    "turn_latency_p95_series": "histogram_quantile(0.95, sum by (le) (rate(ragapp_rag_query_duration_seconds_bucket[${window}])))",
    "ttft_p95_series": "histogram_quantile(0.95, sum by (le) (rate(ragapp_rag_ttft_seconds_bucket[${window}])))",
    "qps_series": "sum(rate(ragapp_rag_queries_total[${window}]))",
    "error_rate_series": _ERROR_RATE,
}

# The single place a validated window becomes a PromQL duration.
_PROMQL_DURATIONS: dict[MetricsWindow, str] = {
    MetricsWindow.HOUR: "5m",
    MetricsWindow.DAY: "5m",
    MetricsWindow.WEEK: "1h",
    MetricsWindow.MONTH: "6h",
}

# Step between points on a range query, chosen so each window yields a
# readable number of points rather than thousands.
_RANGE_STEPS: dict[MetricsWindow, str] = {
    MetricsWindow.HOUR: "1m",
    MetricsWindow.DAY: "15m",
    MetricsWindow.WEEK: "2h",
    MetricsWindow.MONTH: "6h",
}

# Seconds of history each window covers, used to derive a range query's
# start time from its end time.
_WINDOW_SECONDS: dict[MetricsWindow, int] = {
    MetricsWindow.HOUR: 3_600,
    MetricsWindow.DAY: 86_400,
    MetricsWindow.WEEK: 604_800,
    MetricsWindow.MONTH: 2_592_000,
}


def promql_window(window: MetricsWindow) -> str:
    """Return the PromQL rate window for a validated metrics window.

    This is the only conversion from a caller-supplied window to a string
    that reaches a PromQL expression. ``window`` is a ``MetricsWindow``
    member, so no raw user text can ever be interpolated into a query.
    """
    return _PROMQL_DURATIONS[MetricsWindow(window)]


def range_step(window: MetricsWindow) -> str:
    """Return the ``step`` between points for a range query over this window."""
    return _RANGE_STEPS[MetricsWindow(window)]


def window_seconds(window: MetricsWindow) -> int:
    """Return how many seconds of history a validated window covers."""
    return _WINDOW_SECONDS[MetricsWindow(window)]


def render(key: str, window: MetricsWindow, *, range_query: bool = False) -> str:
    """Render one named query for a validated window.

    Args:
        key: A key of ``INSTANT_QUERIES``, or of ``RANGE_QUERIES`` when
            ``range_query`` is set.
        window: The validated window enum member.
        range_query: Read the key from ``RANGE_QUERIES`` instead.

    Returns:
        The PromQL expression with ``${window}`` and ``${range}`` substituted.

    Raises:
        KeyError: If ``key`` names no known query.
    """
    source = RANGE_QUERIES if range_query else INSTANT_QUERIES
    return Template(source[key]).substitute(
        window=promql_window(window),
        range=f"{window_seconds(window)}s",
    )
