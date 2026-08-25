"""Tests for the resilience metric hooks and the no-Prometheus fallback."""
from typing import Any

import pytest

from shared import metrics as metrics_module
from shared import circuit_breaker as circuit_breaker_module
from shared.circuit_breaker import CircuitBreaker, CircuitBreakerOpen, CircuitState
from shared.metrics import METRICS
from shared.rate_limiter import RateLimiter


prometheus = pytest.importorskip("prometheus_client")

SERVICE = circuit_breaker_module._SERVICE_NAME


def gauge_value(metric: Any, **labels: str) -> float:
    """Current value of a labelled gauge."""
    return metric.labels(**labels)._value.get()


def counter_value(metric: Any, **labels: str) -> float:
    """Current value of a labelled counter."""
    return metric.labels(**labels)._value.get()


def _failing_call() -> None:
    raise RuntimeError("downstream is down")


def test_circuit_breaker_transition_sets_the_state_gauge():
    breaker = CircuitBreaker(
        name="metrics-gauge-test",
        failure_threshold=1,
        recovery_timeout=60.0,
    )

    with pytest.raises(RuntimeError):
        breaker.call(_failing_call)

    assert breaker._state is CircuitState.OPEN
    assert (
        gauge_value(
            METRICS.circuit_breaker_state, service=SERVICE, downstream="metrics-gauge-test"
        )
        == 1
    )

    breaker.reset()

    assert (
        gauge_value(
            METRICS.circuit_breaker_state, service=SERVICE, downstream="metrics-gauge-test"
        )
        == 0
    )


def test_circuit_breaker_failure_increments_the_failure_counter():
    breaker = CircuitBreaker(
        name="metrics-failure-test",
        failure_threshold=5,
        recovery_timeout=60.0,
    )
    before = counter_value(
        METRICS.circuit_breaker_failures, service=SERVICE, downstream="metrics-failure-test"
    )

    with pytest.raises(RuntimeError):
        breaker.call(_failing_call)

    assert (
        counter_value(
            METRICS.circuit_breaker_failures, service=SERVICE, downstream="metrics-failure-test"
        )
        == before + 1
    )


def test_open_circuit_rejection_increments_the_rejection_counter():
    breaker = CircuitBreaker(
        name="metrics-rejection-test",
        failure_threshold=1,
        recovery_timeout=60.0,
    )
    with pytest.raises(RuntimeError):
        breaker.call(_failing_call)
    before = counter_value(
        METRICS.circuit_breaker_rejections,
        service=SERVICE,
        downstream="metrics-rejection-test",
    )

    with pytest.raises(CircuitBreakerOpen):
        breaker.call(lambda: "never runs")

    assert (
        counter_value(
            METRICS.circuit_breaker_rejections,
            service=SERVICE,
            downstream="metrics-rejection-test",
        )
        == before + 1
    )


def test_rate_limiter_records_allowed_and_rejected_requests():
    # A capacity of one token lets exactly one request through.
    limiter = RateLimiter(global_rate=1.0, per_ip_rate=1.0, burst_multiplier=1.0)
    before_allowed = counter_value(METRICS.rate_limiter_allowed, service=SERVICE)
    before_rejected = counter_value(METRICS.rate_limiter_rejected, service=SERVICE)

    allowed, _ = limiter.check("198.51.100.7")
    rejected, retry_after = limiter.check("198.51.100.7")

    assert allowed is True
    assert rejected is False
    assert retry_after is not None
    assert counter_value(METRICS.rate_limiter_allowed, service=SERVICE) == before_allowed + 1
    assert counter_value(METRICS.rate_limiter_rejected, service=SERVICE) == before_rejected + 1


def test_dlq_send_counts_the_message_by_error_type():
    class FakeProducer:
        def __init__(self) -> None:
            self.sent = []

        def send(self, topic: str, entry: dict) -> None:
            self.sent.append((topic, entry))

        def flush(self) -> None:
            return None

    from shared.dlq import DeadLetterQueue

    dlq = DeadLetterQueue(producer=FakeProducer(), service_name="metrics-dlq-test")
    before = counter_value(
        METRICS.dlq_messages, service="metrics-dlq-test", error_type="ValueError"
    )

    dlq.send({"correlation_id": "abc"}, error=ValueError("bad payload"))

    assert (
        counter_value(METRICS.dlq_messages, service="metrics-dlq-test", error_type="ValueError")
        == before + 1
    )


def test_metrics_are_silent_when_prometheus_is_not_installed(monkeypatch):
    """Every recording call must be a harmless no-op without prometheus_client."""
    monkeypatch.setattr(metrics_module, "_HAS_PROMETHEUS", False)
    noop = metrics_module.ServiceMetrics()

    # Metrics that exist, used exactly as the instrumented call sites use them.
    noop.rag_ttft_seconds.labels(service="rag", answer_mode="regular").observe(1.5)
    noop.rag_stage_duration.labels(service="rag", stage="rerank").observe(0.2)
    noop.rag_queries_total.labels(service="rag", answer_mode="regular", status="success").inc()
    noop.llm_tokens_total.labels(service="llm_agent", model="m", direction="input").inc(42)
    noop.rpc_roundtrip_seconds.labels(service="rag", downstream="vector_db").observe(0.1)
    noop.ingestion_stage_total.labels(service="files", stage="chunking", outcome="ok").inc()
    noop.circuit_breaker_state.labels(service="rag", downstream="embedding").set(1)
    noop.active_requests.labels(service="rag").dec()
    noop.service_info.info({"service_name": "rag"})

    # And a name that does not exist at all still resolves to the no-op.
    noop.a_metric_that_does_not_exist.labels(service="rag").observe(3.0)
