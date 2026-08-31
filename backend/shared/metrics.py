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
from typing import Any, Optional

from .context import get_context

logger = logging.getLogger("metrics")

TRAFFIC_CLASS_LIVE = "live"
TRAFFIC_CLASS_EVAL = "eval"

# Typed LLM calls currently use a 512-token default. The denser low-end
# buckets distinguish compact guardrail/rewrite/evaluation responses, while
# 768/1024 preserve useful overflow evidence if a bounded request is allowed
# above that default. +Inf remains available through the Prometheus client.
LLM_OUTPUT_TOKEN_BUCKETS = (
    8,
    16,
    32,
    64,
    96,
    128,
    192,
    256,
    384,
    512,
    768,
    1024,
)


# ── Concurrency / saturation baseline vocabulary (CONC-00) ───────────────────
#
# The concurrency track compares every later `CONC-*` change against one
# baseline, so the label vocabularies below are the contract that makes those
# comparisons possible. They are deliberately *closed* sets: a saturation
# dashboard is read while something is on fire, and a series that splits on a
# tenant id, a filename or an exception message is both unreadable and a
# cardinality incident. Nothing here may ever carry tenant ids, user ids,
# request ids, memory ids, filenames, raw exception text or prompts.
#
# These constants are the documented vocabulary, not a runtime validator:
# checking a string on every observation would put a set lookup on the hot
# paths this track exists to make faster. `test_concurrency_metrics.py` holds
# the contract instead, asserting the label *names* stay bounded.

# The nine request classes CONC-00 measures. A `stage` label carries one of
# these, so a baseline artifact and a live dashboard slice the same way.
CONCURRENCY_REQUEST_CLASSES = frozenset({
    "gateway_chat_plain",       # 1. Gateway chat without RAG
    "gateway_chat_rag",         # 2. Gateway/RAG regular chat
    "rag_extended",             # 3. RAG extended retrieval
    "embedding_query",          # 4. embedding query RPC
    "embedding_ingestion",      # 5. embedding ingestion job
    "vector_search",            # 6. vector dense and hybrid search
    "memory_operation",         # 7. Memory read/write/retrieval
    "file_ingestion",           # 8. file upload + ingestion handoff
    "eval_background",          # 9. eval/benchmark background execution
})

# Why a request left the fast path. `unavailable` covers a downstream that was
# not reachable at all; `downstream_error` covers one that answered badly.
DEGRADED_PATH_REASONS = frozenset({
    "busy",
    "timeout",
    "circuit_open",
    "rate_limited",
    "downstream_error",
    "unavailable",
})

# The reranker's four terminal states. `busy` is the one that matters for this
# track: it means a concurrent caller was turned away and the pipeline fell
# back to RRF, which is a quality regression that latency numbers alone hide.
RERANKER_STATUSES = frozenset({"success", "busy", "timeout", "error"})
VLLM_ADMISSION_STATUSES = frozenset(
    {"admitted", "timeout", "closed", "failed", "cancelled"}
)

# Queue wait separates "the service is slow" from "the service never started".
# The dense sub-10ms buckets exist because a healthy in-process handoff should
# be invisible there; anything above 100ms is already backpressure evidence.
QUEUE_WAIT_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

# Event-loop lag is the async equivalent: a loop blocked past ~50ms is running
# something synchronous it should have offloaded.
EVENT_LOOP_LAG_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

# The two scheduling classes the embedding inference scheduler arbitrates
# between (CONC-04). Eval/benchmark work is scheduled as `background`: it is
# throughput work that must never sit in front of an interactive query.
EMBEDDING_SCHEDULER_CLASSES = frozenset({"live", "background"})

# Why the scheduler refused a submission. `closed` is shutdown, not overload.
EMBEDDING_SCHEDULER_REJECTIONS = frozenset({"saturated", "oversized", "closed"})

# Powers of two: batching work is chosen in doublings, so the buckets should
# be able to show a batch size of exactly 1 collapsing into 32.
BATCH_SIZE_BUCKETS = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512)

# Mongo/Qdrant operations on a healthy hot path finish in single-digit
# milliseconds; the long tail is kept so a full-collection scan is visible.
STORE_OPERATION_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

# Decode throughput for one vLLM request. Recorded only when the provider
# actually reported both a token count and a decode duration — a rate this
# process guessed is worse than no rate at all.
OUTPUT_TOKENS_PER_SECOND_BUCKETS = (1, 2, 5, 10, 20, 40, 80, 160, 320, 640)


def traffic_class() -> str:
    """Return the bounded traffic class for the current trusted execution."""
    return TRAFFIC_CLASS_EVAL if get_context().get("traffic_class") == TRAFFIC_CLASS_EVAL else TRAFFIC_CLASS_LIVE

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

        # RPC metrics
        self.rpc_roundtrip_seconds = Histogram(
            "ragapp_rpc_roundtrip_seconds",
            "RabbitMQ RPC round-trip latency by downstream service",
            ["service", "downstream", "traffic_class"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
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

        self.kafka_consumer_lag = Gauge(
            "ragapp_kafka_consumer_lag",
            "Consumer group lag in messages",
            ["service", "topic", "group"],
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

        self.rag_hallucination_total = Counter(
            "ragapp_rag_hallucination_total",
            "Answers by hallucination verdict",
            ["service", "verdict"],  # none | minor | severe
        )

        self.rag_citation_precision = Histogram(
            "ragapp_rag_citation_precision",
            "Per-answer citation precision",
            ["service"],
            buckets=[0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0],
        )

        self.rag_citation_recall = Histogram(
            "ragapp_rag_citation_recall",
            "Per-answer citation recall",
            ["service"],
            buckets=[0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0],
        )

        self.rag_sources_per_query = Histogram(
            "ragapp_rag_sources_per_query",
            "Number of sources retrieved per RAG query",
            ["service"],
            buckets=[0, 1, 2, 3, 5, 8, 10, 15, 20],
        )

        self.rag_ttft_seconds = Histogram(
            "ragapp_rag_ttft_seconds",
            "Time from turn start to first streamed token",
            ["service", "answer_mode"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0],
        )

        self.rag_stage_duration = Histogram(
            "ragapp_rag_stage_duration_seconds",
            "Per-node duration inside the RAG conversation graph",
            ["service", "stage"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
        )

        self.rag_reranker_changed_top1 = Counter(
            "ragapp_rag_reranker_changed_top1_total",
            "Turns where the reranker changed which chunk ranked first",
            ["service", "changed"],  # "true" | "false"
        )

        self.rag_chunks_considered_total = Counter(
            "ragapp_rag_chunks_considered_total",
            "Retrieved chunks that reached the retrieval-policy gate",
            ["service"],
        )

        self.rag_chunks_filtered_total = Counter(
            "ragapp_rag_chunks_filtered_total",
            "Retrieved chunks dropped by retrieval policy",
            ["service", "reason"],  # retrieval_not_allowed | review_removed
        )

        # ── LLM metrics ─────────────────────────────────────────────
        self.llm_requests_total = Counter(
            "ragapp_llm_requests_total",
            "Total LLM generation requests",
            ["service", "model", "request_type", "traffic_class"],
        )

        self.llm_request_duration = Histogram(
            "ragapp_llm_request_duration_seconds",
            "LLM generation latency",
            ["service", "model", "request_type", "traffic_class"],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
        )

        self.llm_provider_duration = Histogram(
            "ragapp_llm_provider_duration_seconds",
            "Time spent inside the observable LLM provider call",
            ["service", "model", "request_type", "traffic_class"],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
        )

        self.llm_tokens_total = Counter(
            "ragapp_llm_tokens_total",
            "LLM tokens by direction",
            ["service", "model", "request_type", "direction", "traffic_class"],
            # direction is bounded to input | output | total
        )

        self.llm_output_tokens = Histogram(
            "ragapp_llm_output_tokens",
            "Output-token count per completed LLM request with reported usage",
            ["service", "request_type", "traffic_class"],
            buckets=LLM_OUTPUT_TOKEN_BUCKETS,
        )

        self.llm_errors_total = Counter(
            "ragapp_llm_errors_total",
            "LLM generation errors",
            ["service", "model", "request_type", "error_type", "traffic_class"],
        )

        # Legacy: mixes the provider's finish reason with application failure
        # state (an application parse failure is counted as `error` here, even
        # when the provider itself finished on `length`). Retained for existing
        # dashboards; use `llm_provider_finish_reasons_total` for provider
        # evidence and `llm_errors_total` for application status.
        self.llm_finish_reasons_total = Counter(
            "ragapp_llm_finish_reasons_total",
            "LLM requests by bounded finish reason (legacy: error-collapsed)",
            ["service", "model", "request_type", "finish_reason", "traffic_class"],
        )

        # The provider's own finish reason, never overwritten by a later
        # application parse/validation failure. `unknown` means no provider
        # response was received at all — it is not an error label.
        self.llm_provider_finish_reasons_total = Counter(
            "ragapp_llm_provider_finish_reasons_total",
            "LLM requests by bounded provider finish reason, free of application state",
            ["service", "model", "request_type", "finish_reason", "traffic_class"],
        )

        # ── Embedding metrics ────────────────────────────────────────
        self.embedding_requests_total = Counter(
            "ragapp_embedding_requests_total",
            "Total embedding requests",
            ["service", "model", "traffic_class"],
        )

        self.embedding_duration = Histogram(
            "ragapp_embedding_duration_seconds",
            "Embedding generation latency",
            ["service", "traffic_class"],
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
            "Learned reranker attempts by deterministic outcome",
            ["service", "status", "traffic_class"],
        )

        self.reranker_duration = Histogram(
            "ragapp_reranker_duration_seconds",
            "Wall time spent awaiting learned reranker inference",
            ["service", "status", "traffic_class"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )

        self.reranker_candidate_count = Histogram(
            "ragapp_reranker_candidate_count",
            "Candidates submitted to one learned reranker attempt",
            ["service", "traffic_class"],
            buckets=[1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 100],
        )

        self.reranker_top_score = Histogram(
            "ragapp_reranker_top_score",
            "Top score produced by successful learned reranking",
            ["service", "traffic_class"],
            buckets=[0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0],
        )

        # ── Vector DB metrics ────────────────────────────────────────
        # Operation counts: one increment per upsert_chunks/delete_chunks
        # call, regardless of how many points that call touched. Use these
        # to track call volume, not collection growth.
        self.vector_upsert_total = Counter(
            "ragapp_vector_upserts_total",
            "Total vector upsert operations (calls, not points)",
            ["service", "collection"],
        )

        self.vector_delete_total = Counter(
            "ragapp_vector_deletes_total",
            "Total vector delete operations (calls, not points)",
            ["service", "collection"],
        )

        # Point counts: incremented by the actual number of points
        # upserted/deleted per call, so they reflect real collection growth.
        self.vector_points_upserted_total = Counter(
            "ragapp_vector_points_upserted_total",
            "Total vector points upserted",
            ["service", "collection"],
        )

        self.vector_points_deleted_total = Counter(
            "ragapp_vector_points_deleted_total",
            "Total vector points deleted",
            ["service", "collection"],
        )

        self.vector_search_total = Counter(
            "ragapp_vector_searches_total",
            "Total vector search operations",
            ["service", "collection", "traffic_class"],
        )

        self.vector_search_duration = Histogram(
            "ragapp_vector_search_duration_seconds",
            "Vector search latency",
            ["service", "collection", "traffic_class"],
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

        self.ingestion_stage_total = Counter(
            "ragapp_ingestion_stage_total",
            "File ingestion stage transitions",
            ["service", "stage", "outcome"],  # ok | failed | skipped
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

        self.memory_operation_duration = Histogram(
            "ragapp_memory_operation_duration_seconds",
            "Memory service operation latency",
            ["service", "operation"],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )

        # failure_class is a fixed vocabulary (embedding, vector_index,
        # database, validation) — never a raw exception message, which would
        # make this series unbounded.
        self.memory_operation_failures_total = Counter(
            "ragapp_memory_operation_failures_total",
            "Memory service operations that failed, by failure class",
            ["service", "operation", "failure_class"],
        )

        self.memory_retrieval_results = Histogram(
            "ragapp_memory_retrieval_results",
            "Memories returned per retrieval call",
            ["service", "retrieval_mode"],  # semantic | lexical
            buckets=[0, 1, 2, 3, 5, 8, 13, 21],
        )

        # outcome is the fixed consolidation vocabulary (create,
        # duplicate_exact, duplicate_semantic, supersede, coexist, historical,
        # needs_review) — never memory text, and never a free-form reason.
        self.memory_consolidation_total = Counter(
            "ragapp_memory_consolidation_total",
            "Memory write consolidation decisions, by outcome",
            ["service", "outcome", "comparison"],  # comparison: semantic | lexical
        )

        # All labels below use closed vocabularies. Memory content, ids,
        # tenant ids, and model error text are deliberately excluded.
        self.memory_agent_runs_total = Counter(
            "ragapp_memory_agent_runs_total",
            "Bounded Memory Agent policy runs by outcome",
            ["service", "operation", "outcome"],
        )

        self.memory_agent_retries_total = Counter(
            "ragapp_memory_agent_retries_total",
            "Memory Agent correction retries by failure class",
            ["service", "retry_class"],
        )

        self.memory_agent_duration = Histogram(
            "ragapp_memory_agent_duration_seconds",
            "End-to-end Memory Agent policy latency",
            ["service", "operation"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0],
        )

        # drift_class and outcome are both closed sets: the reconciler knows
        # every kind of divergence it can find and every way it can end.
        self.memory_reconciliation_total = Counter(
            "ragapp_memory_reconciliation_total",
            "Memory index reconciliation actions, by drift class and outcome",
            ["service", "drift_class", "outcome"],  # outcome: repaired | failed | skipped
        )

        self.memory_reconciliation_duration = Histogram(
            "ragapp_memory_reconciliation_duration_seconds",
            "Duration of one bounded memory reconciliation run",
            ["service"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 15.0, 60.0],
        )

        # ── Concurrency / saturation baseline (CONC-00) ──────────────
        # Everything below is measurement, not control. No handler
        # branches on these; they exist so a later CONC task can prove
        # what it changed. `stage` is always one of
        # CONCURRENCY_REQUEST_CLASSES.
        #
        # `active_requests` above already counts in-flight HTTP work per
        # service. This one is per *request class*, which is what the
        # baseline compares, and covers non-HTTP entry points (RPC
        # handlers, Kafka consumers, background eval) that the HTTP
        # instrumentator never sees.
        self.inflight_by_stage = Gauge(
            "ragapp_inflight_by_stage",
            "Requests/jobs currently executing for one measured request class",
            ["service", "stage"],
        )

        # Time between admission and the handler actually starting. The
        # single most useful saturation signal in the track: it separates
        # a slow handler from a handler that never got a worker.
        self.queue_wait_seconds = Histogram(
            "ragapp_queue_wait_seconds",
            "Wait between accepting work and starting to execute it",
            ["service", "stage"],
            buckets=list(QUEUE_WAIT_BUCKETS),
        )

        # Handler-level duration for entry points that are not HTTP, so
        # RPC and consumer work is comparable with `request_duration`.
        self.handler_duration_seconds = Histogram(
            "ragapp_handler_duration_seconds",
            "Handler execution time for one measured request class",
            ["service", "stage"],
            buckets=[0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
        )

        # Executor saturation. `pool` is a fixed operator-chosen pool
        # name (e.g. "default", "embedding", "reranker"), never a task
        # description. Submitted/rejected are counters because the
        # interesting question is "did we ever shed work"; active/queued/
        # max are gauges sampled from the live pool.
        self.executor_tasks_submitted_total = Counter(
            "ragapp_executor_tasks_submitted_total",
            "Work items handed to a bounded executor",
            ["service", "pool"],
        )

        self.executor_tasks_rejected_total = Counter(
            "ragapp_executor_tasks_rejected_total",
            "Work items refused by a bounded executor (backpressure)",
            ["service", "pool"],
        )

        self.executor_active_workers = Gauge(
            "ragapp_executor_active_workers",
            "Executor workers currently running a task",
            ["service", "pool"],
        )

        self.executor_queue_depth = Gauge(
            "ragapp_executor_queue_depth",
            "Work items waiting for an executor worker",
            ["service", "pool"],
        )

        self.executor_max_workers = Gauge(
            "ragapp_executor_max_workers",
            "Configured worker ceiling for an executor",
            ["service", "pool"],
        )

        # RPC saturation alongside the existing rpc_roundtrip_seconds.
        # A timeout is counted separately because it never produces a
        # round-trip observation, so the histogram alone under-reports
        # exactly the failure the track is trying to remove.
        self.rpc_timeouts_total = Counter(
            "ragapp_rpc_timeouts_total",
            "RabbitMQ RPC calls that expired without a reply",
            ["service", "downstream"],
        )

        self.rpc_inflight = Gauge(
            "ragapp_rpc_inflight",
            "RPC calls awaiting a reply from one downstream service",
            ["service", "downstream"],
        )

        # Consumer-side RabbitMQ. `queue` is a fixed declared queue name.
        self.rabbitmq_deliveries_total = Counter(
            "ragapp_rabbitmq_deliveries_total",
            "Messages delivered to a RabbitMQ consumer",
            ["service", "queue"],
        )

        self.rabbitmq_inflight_deliveries = Gauge(
            "ragapp_rabbitmq_inflight_deliveries",
            "Delivered RabbitMQ messages not yet acked/nacked",
            ["service", "queue"],
        )

        # Async health. Sampled by a probe, never by a request path.
        self.event_loop_lag_seconds = Histogram(
            "ragapp_event_loop_lag_seconds",
            "Delay beyond the requested sleep for a service's event loop",
            ["service"],
            buckets=list(EVENT_LOOP_LAG_BUCKETS),
        )

        # `kind` is a fixed operator vocabulary ("persistence", "eval",
        # "reconciliation", ...), never a task name or an id.
        self.background_tasks = Gauge(
            "ragapp_background_tasks",
            "Background tasks currently alive, by fixed kind",
            ["service", "kind"],
        )

        # Every departure from the fast path. `reason` is one of
        # DEGRADED_PATH_REASONS — a closed set, never an exception string.
        self.degraded_path_total = Counter(
            "ragapp_degraded_path_total",
            "Requests served by a fallback/degraded path",
            ["service", "stage", "reason"],
        )

        # `mode` is "query" or "ingestion": the two embedding call shapes
        # have opposite batching economics and must not be averaged.
        self.embedding_batch_size = Histogram(
            "ragapp_embedding_batch_size",
            "Texts embedded per encode call",
            ["service", "mode"],
            buckets=list(BATCH_SIZE_BUCKETS),
        )

        # ── Embedding inference scheduler (CONC-04) ─────────────────
        #
        # `embedding_class` is the closed pair in EMBEDDING_SCHEDULER_CLASSES:
        # interactive work and everything deferrable. It is deliberately not
        # the `traffic_class` label — eval traffic is scheduled as background
        # here, and collapsing the two would hide exactly the fairness the
        # scheduler exists to provide.
        self.embedding_scheduler_pending_items = Gauge(
            "ragapp_embedding_scheduler_pending_items",
            "Embedding items accepted by the inference scheduler and not yet embedded",
            ["service", "embedding_class"],
        )

        # One observation per physical model forward pass, so it can be read
        # against embedding_batch_size: the same wall time spread over a
        # larger batch is the whole point of micro-batching.
        self.embedding_inference_duration_seconds = Histogram(
            "ragapp_embedding_inference_duration_seconds",
            "Wall time of one physical embedding model forward pass",
            ["service"],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )

        # `reason` is one of EMBEDDING_SCHEDULER_REJECTIONS, never a message.
        self.embedding_scheduler_rejected_total = Counter(
            "ragapp_embedding_scheduler_rejected_total",
            "Embedding submissions refused by the bounded inference scheduler",
            ["service", "embedding_class", "reason"],
        )

        # Distinct from reranker_candidate_count: that is how many
        # candidates the pipeline had, this is how many were sent to the
        # model in one forward pass. CONC-05 changes the second, not the
        # first, and conflating them would hide the change.
        self.reranker_batch_size = Histogram(
            "ragapp_reranker_batch_size",
            "Pairs scored per reranker forward pass",
            ["service"],
            buckets=list(BATCH_SIZE_BUCKETS),
        )

        # `status` is one of RERANKER_STATUSES. `busy` is the reason this
        # metric exists: it is a silent quality regression under load.
        self.reranker_status_total = Counter(
            "ragapp_reranker_status_total",
            "Reranker outcomes by terminal status",
            ["service", "status"],
        )

        # Provider-level vLLM evidence, separate from the RAG-level
        # rag_ttft_seconds: one measures the model, the other the whole
        # pipeline, and CONC-03 must be able to tell them apart.
        self.vllm_inflight_requests = Gauge(
            "ragapp_vllm_inflight_requests",
            "Requests this service currently has open against vLLM",
            ["service"],
        )

        self.vllm_configured_limit = Gauge(
            "ragapp_vllm_configured_limit",
            "Configured process-wide vLLM inference capacity",
            ["service"],
        )

        self.vllm_admission_wait_seconds = Histogram(
            "ragapp_vllm_admission_wait_seconds",
            "Time spent waiting for shared vLLM inference capacity",
            ["service", "traffic_class"],
            buckets=list(QUEUE_WAIT_BUCKETS),
        )

        self.vllm_admission_outcomes_total = Counter(
            "ragapp_vllm_admission_outcomes_total",
            "Shared vLLM admission outcomes",
            ["service", "traffic_class", "status"],
        )

        self.vllm_ttft_seconds = Histogram(
            "ragapp_vllm_ttft_seconds",
            "Time to first token from vLLM, when the provider streams it",
            ["service"],
            buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0],
        )

        self.vllm_output_tokens_per_second = Histogram(
            "ragapp_vllm_output_tokens_per_second",
            "Decode throughput for one vLLM request, when measurable",
            ["service"],
            buckets=list(OUTPUT_TOKENS_PER_SECOND_BUCKETS),
        )

        # Store latency around the hot paths CONC-07 and VECTOR-02 own.
        # `collection` is a fixed schema collection name; it is never a
        # tenant-scoped or per-document name.
        self.mongo_operation_duration = Histogram(
            "ragapp_mongo_operation_duration_seconds",
            "Mongo operation latency on an identified hot path",
            ["service", "collection", "operation"],
            buckets=list(STORE_OPERATION_BUCKETS),
        )

        # Complements vector_search_duration, which covers search only.
        self.qdrant_operation_duration = Histogram(
            "ragapp_qdrant_operation_duration_seconds",
            "Qdrant operation latency on an identified hot path",
            ["service", "operation"],
            buckets=list(STORE_OPERATION_BUCKETS),
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


def observe_kafka_consumer_lag(
    service: str,
    topic: str,
    group: str,
    highwater: Optional[int],
    next_offset: Optional[int],
) -> Optional[int]:
    """Record consumer lag from two offsets the consume path already holds.

    Lag is ``highwater - next_offset``: both are *next* offsets, so a caught-up
    consumer is genuinely 0 and the subtraction needs no correction.

    An unknown offset records **nothing** and returns None. kafka-python
    reports ``highwater`` only once a FetchResponse has arrived for that
    partition, and a gauge that reads 0 because the offset was unavailable is
    indistinguishable from a consumer that is keeping up — the worse of the two
    failures, since it is the reading an operator would trust.

    Lives here rather than in ``kafka_base`` on purpose: kafka-python is in no
    shared requirements file, so ``shared/kafka_base.py`` cannot be imported by
    the shared test job at all. Keeping the arithmetic in this kafka-free
    module is what makes it testable rather than permanently skipped.

    Args:
        service: Recording service name, the gauge's ``service`` label.
        topic: Topic the message came from.
        group: Consumer group id.
        highwater: Next offset the broker will assign, or None if unknown.
        next_offset: Next offset this consumer will read, or None if unknown.

    Returns:
        The recorded lag, or None when nothing was recorded.
    """
    if highwater is None or next_offset is None:
        return None
    lag = max(0, int(highwater) - int(next_offset))
    METRICS.kafka_consumer_lag.labels(service=service, topic=topic, group=group).set(lag)
    return lag


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
        excluded_handlers=["/health", "/live", "/ready", "/metrics"],
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
