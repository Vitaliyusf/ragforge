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
    EVENT_LOOP_LAG_BUCKETS,
    METRICS,
    QUEUE_WAIT_BUCKETS,
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
    "reranker_batch_size",
    "reranker_status_total",
    "vllm_inflight_requests",
    "vllm_ttft_seconds",
    "vllm_output_tokens_per_second",
    "mongo_operation_duration",
    "qdrant_operation_duration",
)


def _labels(name: str) -> tuple:
    return tuple(getattr(METRICS, name)._labelnames)


def test_every_required_signal_has_a_metric():
    """The task names the signals; this asserts none was quietly dropped."""
    for name in CONCURRENCY_METRICS:
        assert hasattr(METRICS, name), f"missing concurrency metric: {name}"


@pytest.mark.parametrize("name", CONCURRENCY_METRICS)
def test_concurrency_metric_labels_stay_bounded(name: str):
    labels = {label.lower() for label in _labels(name)}
    offenders = labels & FORBIDDEN_LABELS
    assert not offenders, f"{name} carries unbounded labels: {sorted(offenders)}"


@pytest.mark.parametrize("name", CONCURRENCY_METRICS)
def test_every_concurrency_metric_is_attributed_to_a_service(name: str):
    assert "service" in _labels(name), f"{name} cannot be attributed to a service"


def test_the_stage_label_carries_the_nine_measured_request_classes():
    for name in ("inflight_by_stage", "queue_wait_seconds", "handler_duration_seconds", "degraded_path_total"):
        assert "stage" in _labels(name)
    assert len(CONCURRENCY_REQUEST_CLASSES) == 9


def test_the_closed_vocabularies_are_immutable():
    """A mutable default would let one import order change another service's
    label space."""
    for vocabulary in (CONCURRENCY_REQUEST_CLASSES, DEGRADED_PATH_REASONS, RERANKER_STATUSES):
        assert isinstance(vocabulary, frozenset)


def test_reranker_statuses_are_exactly_the_four_the_task_names():
    assert RERANKER_STATUSES == {"success", "busy", "timeout", "error"}


def test_bucket_edges_are_documented_and_ascending():
    for buckets in (QUEUE_WAIT_BUCKETS, EVENT_LOOP_LAG_BUCKETS, BATCH_SIZE_BUCKETS):
        assert list(buckets) == sorted(buckets)
        assert len(set(buckets)) == len(buckets)


def test_queue_wait_histogram_uses_the_documented_buckets():
    observed = tuple(METRICS.queue_wait_seconds._upper_bounds[:-1])
    assert observed == tuple(float(bucket) for bucket in QUEUE_WAIT_BUCKETS)


def test_degraded_path_records_a_closed_reason_vocabulary():
    metric = cast(Any, METRICS.degraded_path_total)
    before = metric.labels(service="s", stage="rag_extended", reason="busy")._value.get()
    metric.labels(service="s", stage="rag_extended", reason="busy").inc()
    assert metric.labels(service="s", stage="rag_extended", reason="busy")._value.get() == before + 1
    assert "busy" in DEGRADED_PATH_REASONS


def test_reranker_batch_size_is_distinct_from_candidate_count():
    """CONC-05 changes the batch, not the candidate pool; one metric for both
    would hide exactly the change it is meant to prove."""
    assert METRICS.reranker_batch_size is not METRICS.reranker_candidate_count
