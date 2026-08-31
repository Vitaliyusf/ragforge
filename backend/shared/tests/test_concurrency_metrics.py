"""The CONC-00 metric contract: bounded labels and a stable vocabulary.

The whole concurrency track compares later runs against one baseline, so these
label names are an interface. They are also the repository's cardinality
guard: a saturation dashboard is read while something is on fire, and a series
that splits on a tenant id, a filename or an exception message is both
unreadable and an incident of its own.
"""
from typing import Any, cast

import pytest

from shared.metrics import (
    BATCH_SIZE_BUCKETS,
    CONCURRENCY_REQUEST_CLASSES,
    DEGRADED_PATH_REASONS,
    EMBEDDING_SCHEDULER_CLASSES,
    EMBEDDING_SCHEDULER_REJECTIONS,
    EMBEDDING_SCHEDULER_TIMEOUT_PHASES,
    EVENT_LOOP_LAG_BUCKETS,
    METRICS,
    MODEL_LOAD_OUTCOMES,
    QUEUE_WAIT_BUCKETS,
    RERANKER_SCHEDULER_CAPACITY_SETTINGS,
    RERANKER_SCHEDULER_CLASSES,
    RERANKER_SCHEDULER_REJECTIONS,
    RERANKER_SCHEDULER_TIMEOUT_PHASES,
    RERANKER_STATUSES,
)

prometheus = pytest.importorskip("prometheus_client")


# Label names that would make a series unbounded. Checked against every
# concurrency metric below, so a later task cannot add one by accident.
FORBIDDEN_LABELS = frozenset(
    {
        "tenant",
        "tenant_id",
        "user",
        "user_id",
        "request_id",
        "trace_id",
        "memory_id",
        "document_id",
        "file_id",
        "filename",
        "prompt",
        "query",
        "error",
        "exception",
        "message",
    }
)

CONCURRENCY_METRICS = (
    "inflight_by_stage",
    "queue_wait_seconds",
    "handler_duration_seconds",
    "executor_tasks_submitted_total",
    "executor_tasks_rejected_total",
    "executor_active_workers",
    "executor_queue_depth",
    "executor_max_workers",
    "rpc_timeouts_total",
    "rpc_inflight",
    "rabbitmq_deliveries_total",
    "rabbitmq_inflight_deliveries",
    "event_loop_lag_seconds",
    "background_tasks",
    "degraded_path_total",
    "embedding_batch_size",
    "embedding_scheduler_pending_items",
    "embedding_scheduler_rejected_total",
    "embedding_scheduler_items_total",
    "embedding_scheduler_latency_seconds",
    "embedding_scheduler_timeouts_total",
    "embedding_inference_duration_seconds",
    "model_loads_total",
    "reranker_batch_size",
    "reranker_status_total",
    "reranker_scheduler_pending_requests",
    "reranker_scheduler_pending_pairs",
    "reranker_scheduler_queue_wait_seconds",
    "reranker_inference_duration_seconds",
    "reranker_scheduler_rejected_total",
    "reranker_scheduler_timeouts_total",
    "reranker_scheduler_pairs_total",
    "reranker_scheduler_capacity",
    "vllm_inflight_requests",
    "vllm_configured_limit",
    "vllm_admission_wait_seconds",
    "vllm_admission_outcomes_total",
    "vllm_ttft_seconds",
    "vllm_output_tokens_per_second",
    "mongo_operation_duration",
    "qdrant_operation_duration",
)


def _labels(name: str) -> tuple[str, ...]:
    return tuple(str(label) for label in getattr(METRICS, name)._labelnames)


def test_every_required_signal_has_a_metric() -> None:
    """The task names the signals; this asserts none was quietly dropped."""
    for name in CONCURRENCY_METRICS:
        assert hasattr(METRICS, name), f"missing concurrency metric: {name}"


@pytest.mark.parametrize("name", CONCURRENCY_METRICS)
def test_concurrency_metric_labels_stay_bounded(name: str) -> None:
    labels = {label.lower() for label in _labels(name)}
    offenders = labels & FORBIDDEN_LABELS
    assert not offenders, f"{name} carries unbounded labels: {sorted(offenders)}"


@pytest.mark.parametrize("name", CONCURRENCY_METRICS)
def test_every_concurrency_metric_is_attributed_to_a_service(name: str) -> None:
    assert "service" in _labels(name), f"{name} cannot be attributed to a service"


def test_the_stage_label_carries_the_nine_measured_request_classes() -> None:
    for name in ("inflight_by_stage", "queue_wait_seconds", "handler_duration_seconds", "degraded_path_total"):
        assert "stage" in _labels(name)
    assert len(CONCURRENCY_REQUEST_CLASSES) == 9


def test_the_closed_vocabularies_are_immutable() -> None:
    """A mutable default would let one import order change another service's
    label space."""
    for vocabulary in (
        CONCURRENCY_REQUEST_CLASSES,
        DEGRADED_PATH_REASONS,
        RERANKER_STATUSES,
        EMBEDDING_SCHEDULER_CLASSES,
        EMBEDDING_SCHEDULER_REJECTIONS,
        EMBEDDING_SCHEDULER_TIMEOUT_PHASES,
        RERANKER_SCHEDULER_CLASSES,
        RERANKER_SCHEDULER_REJECTIONS,
        RERANKER_SCHEDULER_TIMEOUT_PHASES,
        RERANKER_SCHEDULER_CAPACITY_SETTINGS,
        MODEL_LOAD_OUTCOMES,
    ):
        assert isinstance(vocabulary, frozenset)


def test_reranker_statuses_are_exactly_the_four_the_task_names() -> None:
    assert RERANKER_STATUSES == {"success", "busy", "timeout", "error"}


def test_the_rerank_scheduler_vocabularies_stay_closed() -> None:
    """CONC-05 label spaces, pinned so a later task cannot widen them."""
    assert RERANKER_SCHEDULER_CLASSES == {"live", "background"}
    assert RERANKER_SCHEDULER_REJECTIONS == {"saturated", "oversized", "closed"}
    assert RERANKER_SCHEDULER_TIMEOUT_PHASES == {"admission", "inference"}
    assert RERANKER_SCHEDULER_CAPACITY_SETTINGS == {
        "max_pending_pairs",
        "max_batch_pairs",
        "inference_workers",
        "max_background_inflight",
    }


def test_bucket_edges_are_documented_and_ascending() -> None:
    for buckets in (QUEUE_WAIT_BUCKETS, EVENT_LOOP_LAG_BUCKETS, BATCH_SIZE_BUCKETS):
        assert list(buckets) == sorted(buckets)
        assert len(set(buckets)) == len(buckets)


def test_queue_wait_histogram_uses_the_documented_buckets() -> None:
    observed = tuple(METRICS.queue_wait_seconds._upper_bounds[:-1])
    assert observed == tuple(float(bucket) for bucket in QUEUE_WAIT_BUCKETS)


def test_degraded_path_records_a_closed_reason_vocabulary() -> None:
    metric = cast(Any, METRICS.degraded_path_total)
    before = metric.labels(service="s", stage="rag_extended", reason="busy")._value.get()
    metric.labels(service="s", stage="rag_extended", reason="busy").inc()
    assert metric.labels(service="s", stage="rag_extended", reason="busy")._value.get() == before + 1
    assert "busy" in DEGRADED_PATH_REASONS


def test_the_embedding_scheduler_signals_split_live_from_background() -> None:
    """The fairness claim is unreadable on a series that averages the two."""
    for name in (
        "embedding_scheduler_pending_items",
        "embedding_scheduler_rejected_total",
        "embedding_scheduler_items_total",
        "embedding_scheduler_timeouts_total",
        "embedding_scheduler_latency_seconds",
    ):
        assert "embedding_class" in _labels(name), name
    assert EMBEDDING_SCHEDULER_CLASSES == {"live", "background"}


def test_items_processed_is_a_counter_so_the_rate_is_the_dashboard_s_choice() -> None:
    """CONC-04 asks for items/sec. A gauge would bake one averaging window in
    here; a monotonic counter lets `rate()` pick it at read time, and the same
    series then also answers whether background is still progressing."""
    metric = cast(Any, METRICS.embedding_scheduler_items_total)
    labels = {"service": "probe_service", "embedding_class": "background"}
    before = metric.labels(**labels)._value.get()
    metric.labels(**labels).inc(4)
    assert metric.labels(**labels)._value.get() == before + 4
    assert isinstance(METRICS.embedding_scheduler_items_total, prometheus.Counter)


def test_per_class_latency_is_one_histogram_not_two_halves() -> None:
    """queue wait and inference duration each measure half of what a live
    request actually pays; the fairness criterion is stated on the sum."""
    assert METRICS.embedding_scheduler_latency_seconds is not METRICS.queue_wait_seconds
    assert (
        METRICS.embedding_scheduler_latency_seconds
        is not METRICS.embedding_inference_duration_seconds
    )
    observed = tuple(METRICS.embedding_scheduler_latency_seconds._upper_bounds[:-1])
    assert observed == tuple(float(bucket) for bucket in QUEUE_WAIT_BUCKETS)


def test_scheduler_timeouts_are_counted_apart_from_rejections() -> None:
    """A rejection is refused immediately; a timeout costs the caller its whole
    deadline. Collapsing them hides which one an operator is looking at."""
    assert METRICS.embedding_scheduler_timeouts_total is not (
        METRICS.embedding_scheduler_rejected_total
    )
    assert "phase" in _labels("embedding_scheduler_timeouts_total")
    assert EMBEDDING_SCHEDULER_TIMEOUT_PHASES == {"admission", "inference"}
    assert EMBEDDING_SCHEDULER_REJECTIONS == {"saturated", "oversized", "closed"}


def test_model_load_outcomes_are_a_closed_pair() -> None:
    """The point of the counter is a second increment: a reloaded model is a
    second copy of the weights, which breaks the one-instance contract."""
    assert MODEL_LOAD_OUTCOMES == {"success", "failure"}
    assert set(_labels("model_loads_total")) == {"service", "model_kind", "outcome"}
    assert isinstance(METRICS.model_loads_total, prometheus.Counter)


def test_reranker_batch_size_is_distinct_from_candidate_count() -> None:
    """CONC-05 changes the batch, not the candidate pool; one metric for both
    would hide exactly the change it is meant to prove."""
    assert METRICS.reranker_batch_size is not METRICS.reranker_candidate_count


# ── wiring at the shared boundaries ─────────────────────────
#
# A declared metric is not an instrumented one. These prove the two shared
# consumer boundaries actually record, so `CONCURRENCY_BASELINE.md` can call
# them WIRED rather than DECLARED.


def _gauge_value(metric: Any, **labels: str) -> float:
    value = cast(Any, metric).labels(**labels)._value.get()
    return float(value)


def _counter_value(metric: Any, **labels: str) -> float:
    value = cast(Any, metric).labels(**labels)._value.get()
    return float(value)


def test_the_shared_rabbitmq_consumer_records_delivery_and_inflight() -> None:
    pytest.importorskip("aio_pika")
    import asyncio

    from shared.rabbitmq_base import BaseRabbitMQConsumer

    class Config:
        rabbitmq_url = "amqp://localhost"
        rabbitmq_exchange = "ragapp.requests"
        rabbitmq_queue = "probe_queue"
        rabbitmq_prefetch_count = 1
        service_name = "probe_service"

    seen: list[float] = []

    class Consumer(BaseRabbitMQConsumer):
        async def _dispatch_message(self, message: Any, handler: Any) -> None:
            del message, handler
            seen.append(
                _gauge_value(
                    METRICS.rabbitmq_inflight_deliveries,
                    service="probe_service",
                    queue="probe_queue",
                )
            )

    labels = {"service": "probe_service", "queue": "probe_queue"}
    delivered_before = _counter_value(METRICS.rabbitmq_deliveries_total, **labels)
    inflight_before = _gauge_value(METRICS.rabbitmq_inflight_deliveries, **labels)

    asyncio.run(Consumer(Config())._dispatch(cast(Any, object()), cast(Any, None)))

    assert _counter_value(METRICS.rabbitmq_deliveries_total, **labels) == delivered_before + 1
    assert seen == [inflight_before + 1], "the delivery must be in flight while it runs"
    assert _gauge_value(METRICS.rabbitmq_inflight_deliveries, **labels) == inflight_before


def test_a_failed_rabbitmq_delivery_still_releases_the_inflight_gauge() -> None:
    """A gauge that only decrements on success drifts upward forever and reads
    as permanent saturation — the reading an operator would act on."""
    pytest.importorskip("aio_pika")
    import asyncio

    from shared.rabbitmq_base import BaseRabbitMQConsumer

    class Config:
        rabbitmq_url = "amqp://localhost"
        rabbitmq_exchange = "ragapp.requests"
        rabbitmq_queue = "failing_queue"
        rabbitmq_prefetch_count = 1
        service_name = "probe_service"

    class Consumer(BaseRabbitMQConsumer):
        async def _dispatch_message(self, message: Any, handler: Any) -> None:
            del message, handler
            raise RuntimeError("handler failed")

    labels = {"service": "probe_service", "queue": "failing_queue"}
    before = _gauge_value(METRICS.rabbitmq_inflight_deliveries, **labels)

    with pytest.raises(RuntimeError):
        asyncio.run(Consumer(Config())._dispatch(cast(Any, object()), cast(Any, None)))

    assert _gauge_value(METRICS.rabbitmq_inflight_deliveries, **labels) == before


def test_the_shared_kafka_consumer_times_the_work_it_hands_out() -> None:
    pytest.importorskip("kafka")

    from shared.kafka_base import BaseKafkaConsumer

    class Message:
        topic = "probe_topic"
        partition = 0
        offset = 0
        value = {"payload": 1}

    class Consumer(BaseKafkaConsumer):
        def _init_consumer(self) -> bool:
            return True

        def _record_lag(self, message: Any) -> None:
            del message
            return None

    consumer = Consumer.__new__(Consumer)
    cast(Any, consumer).config = type("C", (), {"service_name": "probe_service"})()
    cast(Any, consumer)._consumer = [Message()]

    histogram = cast(Any, METRICS.kafka_message_processing_duration)
    labels = {"service": "probe_service", "topic": "probe_topic"}
    before = histogram.labels(**labels)._sum.get()

    assert [message for message in consumer.consume()] == [{"payload": 1}]

    # Observed at all, and not the broker's wait: the timer starts when the
    # message leaves the generator, so it measures the consumer's own work.
    assert histogram.labels(**labels)._sum.get() >= before
    observations = [
        sample.value
        for metric in histogram.collect()
        for sample in metric.samples
        if sample.name.endswith("_count") and sample.labels.get("topic") == "probe_topic"
    ]
    assert observations == [1.0], "exactly one message, exactly one observation"
