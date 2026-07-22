"""Prometheus metrics for all microservices.

Provides custom metrics for monitoring service health, performance,
and resilience patterns (circuit breakers, rate limiting, DLQ).

Usage:
    from shared.metrics import setup_metrics, METRICS

    # In main.py:
    setup_metrics(app, service_name="gateway")

    # Recording metrics:
    METRICS.request_count.labels(service="gateway", endpoint="/v1/chat").inc()
    METRICS.request_duration.labels(service="gateway").observe(0.5)
    METRICS.circuit_breaker_state.labels(service="embedding").set(0)  # 0=closed, 1=open, 2=half_open
"""
import logging
from typing import Any

logger = logging.getLogger("metrics")

try:
    from prometheus_client import Counter, Histogram, Gauge, Info
    from prometheus_fastapi_instrumentator import Instrumentator
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False


class ServiceMetrics:
    """Container for all custom Prometheus metrics."""

    def __init__(self) -> None:
        if not _HAS_PROMETHEUS:
            self._noop = True
            return
        self._noop = False

        # Request metrics
        self.request_count = Counter(
            "ragapp_requests_total",
            "Total number of requests",
            ["service", "endpoint", "method", "status"],
        )

        self.request_duration = Histogram(
            "ragapp_request_duration_seconds",
            "Request duration in seconds",
            ["service", "endpoint"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
        )

        # Kafka metrics
        self.kafka_messages_produced = Counter(
            "ragapp_kafka_messages_produced_total",
            "Total Kafka messages produced",
            ["service", "topic"],
        )

        self.kafka_messages_consumed = Counter(
            "ragapp_kafka_messages_consumed_total",
            "Total Kafka messages consumed",
            ["service", "topic"],
        )

        self.kafka_message_processing_duration = Histogram(
            "ragapp_kafka_message_processing_seconds",
            "Kafka message processing duration",
            ["service", "topic"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
        )

        # Circuit breaker metrics
        self.circuit_breaker_state = Gauge(
            "ragapp_circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open, 2=half_open)",
            ["service", "downstream"],
        )

        self.circuit_breaker_failures = Counter(
            "ragapp_circuit_breaker_failures_total",
            "Circuit breaker failure count",
            ["service", "downstream"],
        )

        self.circuit_breaker_rejections = Counter(
            "ragapp_circuit_breaker_rejections_total",
            "Requests rejected by open circuit breaker",
            ["service", "downstream"],
        )

        # Rate limiter metrics
        self.rate_limiter_allowed = Counter(
            "ragapp_rate_limiter_allowed_total",
            "Requests allowed by rate limiter",
            ["service"],
        )

        self.rate_limiter_rejected = Counter(
            "ragapp_rate_limiter_rejected_total",
            "Requests rejected by rate limiter",
            ["service"],
        )

        # DLQ metrics
        self.dlq_messages = Counter(
            "ragapp_dlq_messages_total",
            "Messages sent to dead letter queue",
            ["service", "error_type"],
        )

        # Active connections
        self.active_requests = Gauge(
            "ragapp_active_requests",
            "Currently active requests",
            ["service"],
        )

        # Service info
        self.service_info = Info(
            "ragapp_service",
            "Service information",
        )

        # ── RAG pipeline metrics ─────────────────────────────────────
        self.rag_queries_total = Counter(
            "ragapp_rag_queries_total",
            "Total RAG queries processed",
            ["service", "answer_mode", "status"],
        )

        self.rag_query_duration = Histogram(
            "ragapp_rag_query_duration_seconds",
            "End-to-end RAG query latency",
            ["service", "answer_mode"],
            buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0],
        )

        self.rag_retrieval_score = Histogram(
            "ragapp_rag_retrieval_score",
            "RAG retrieval quality score distribution (0-1)",
            ["service"],
            buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        )

        self.rag_confidence_level = Counter(
            "ragapp_rag_confidence_total",
            "RAG answer confidence levels",
            ["service", "level"],  # high, medium, low
        )

        self.rag_sources_per_query = Histogram(
            "ragapp_rag_sources_per_query",
            "Number of sources retrieved per RAG query",
            ["service"],
            buckets=[0, 1, 2, 3, 5, 8, 10, 15, 20],
        )

        # ── LLM metrics ─────────────────────────────────────────────
        self.llm_requests_total = Counter(
            "ragapp_llm_requests_total",
            "Total LLM generation requests",
            ["service", "model", "action"],
        )

        self.llm_request_duration = Histogram(
            "ragapp_llm_request_duration_seconds",
            "LLM generation latency",
            ["service", "model"],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
        )

        self.llm_tokens_generated = Counter(
            "ragapp_llm_tokens_generated_total",
            "Total tokens generated by LLM",
            ["service", "model"],
        )

        self.llm_errors_total = Counter(
            "ragapp_llm_errors_total",
            "LLM generation errors",
            ["service", "model", "error_type"],
        )

        # ── Embedding metrics ────────────────────────────────────────
        self.embedding_requests_total = Counter(
            "ragapp_embedding_requests_total",
            "Total embedding requests",
            ["service", "model"],
        )

        self.embedding_duration = Histogram(
            "ragapp_embedding_duration_seconds",
            "Embedding generation latency",
            ["service"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
        )

        self.embedding_chunks_processed = Counter(
            "ragapp_embedding_chunks_total",
            "Total document chunks embedded",
            ["service"],
        )

        # ── Reranker metrics ─────────────────────────────────────────
        self.reranker_requests_total = Counter(
            "ragapp_reranker_requests_total",
            "Total reranker requests",
            ["service"],
        )

        self.reranker_duration = Histogram(
            "ragapp_reranker_duration_seconds",
            "Reranker scoring latency",
            ["service"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
        )

        self.reranker_top_score = Histogram(
            "ragapp_reranker_top_score",
            "Top reranker score per query",
            ["service"],
            buckets=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        )

        # ── Vector DB metrics ────────────────────────────────────────
        self.vector_upsert_total = Counter(
            "ragapp_vector_upserts_total",
            "Total vector upsert operations",
            ["service", "collection"],
        )

        self.vector_search_total = Counter(
            "ragapp_vector_searches_total",
            "Total vector search operations",
            ["service", "collection"],
        )

        self.vector_search_duration = Histogram(
            "ragapp_vector_search_duration_seconds",
            "Vector search latency",
            ["service", "collection"],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )

        # ── File pipeline metrics ────────────────────────────────────
        self.file_uploads_total = Counter(
            "ragapp_file_uploads_total",
            "Total file uploads",
            ["service", "file_type"],
        )

        self.file_processing_duration = Histogram(
            "ragapp_file_processing_duration_seconds",
            "File ingestion pipeline total duration",
            ["service", "stage"],  # extraction, chunking, embedding, vectorization
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
        )

        # ── WebSocket / streaming metrics ────────────────────────────
        self.websocket_connections = Gauge(
            "ragapp_websocket_connections",
            "Active WebSocket/Socket.IO connections",
            ["service"],
        )

        self.stream_tokens_emitted = Counter(
            "ragapp_stream_tokens_emitted_total",
            "Total streaming tokens emitted to clients",
            ["service"],
        )

        # ── Memory service metrics ───────────────────────────────────
        self.memory_operations_total = Counter(
            "ragapp_memory_operations_total",
            "Total memory service operations",
            ["service", "operation"],  # create_chat, add_message, delete_chat, write_memory
        )

    def __getattr__(self, name: str) -> Any:
        """Return no-op for any metric access when Prometheus is not installed."""
        if self._noop:
            return _NoOpMetric()
        raise AttributeError(name)


class _NoOpMetric:
    """No-op metric for when Prometheus is not installed."""
    def labels(self, **kwargs: Any) -> "_NoOpMetric":
        return self
    def inc(self, amount: float = 1) -> None: pass
    def dec(self, amount: float = 1) -> None: pass
    def set(self, value: float) -> None: pass
    def observe(self, value: float) -> None: pass
    def info(self, value: Any) -> None: pass


# Singleton metrics instance
METRICS = ServiceMetrics()


def setup_metrics(app: Any, service_name: str, enable_tracing: bool = True) -> None:
    """
    Setup Prometheus metrics and instrumentation for a FastAPI app.

    Adds:
    - Auto-instrumentation for all HTTP endpoints
    - /metrics endpoint for Prometheus scraping
    - Custom metrics registration
    - OpenTelemetry tracing (if enable_tracing=True and deps available)

    Args:
        app: FastAPI application
        service_name: Name of the service
        enable_tracing: Also initialize OpenTelemetry tracing
    """
    if not _HAS_PROMETHEUS:
        logger.warning(
            f"Prometheus client not installed for {service_name}. "
            "Install with: pip install prometheus-client prometheus-fastapi-instrumentator"
        )
        return

    # Auto-instrument all HTTP endpoints
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    )
    instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/metrics", tags=["monitoring"])

    # Set service info
    METRICS.service_info.info({
        "service_name": service_name,
        "version": "1.0.0",
    })

    logger.info(f"Prometheus metrics initialized for {service_name} at /metrics")

    # Initialize distributed tracing
    if enable_tracing:
        try:
            from shared.tracing import init_tracing
            import os
            otlp_endpoint = os.environ.get("OTLP_ENDPOINT", "http://jaeger:4317")
            init_tracing(service_name, otlp_endpoint=otlp_endpoint)
        except Exception as e:
            logger.info(f"Tracing not initialized for {service_name}: {e}")
