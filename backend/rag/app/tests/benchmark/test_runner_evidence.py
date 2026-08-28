"""Operational evidence captured around a benchmark run."""
from __future__ import annotations



from app.services.benchmark_prometheus import SNAPSHOT_QUERIES
from app.services.benchmark_runner import (
    PHASE_RETRIEVAL_BASE,
)
from app.services.eval_store import (
    BENCHMARK_COMPLETED,
)


from app.tests.benchmark._harness import (
    FakeSnapshotter,
    build,
    fetch,
    run_benchmark,
)

def test_a_benchmark_stores_before_and_after_operational_snapshots():
    before = {"prometheus_available": True, "sections": {"overview": {"qps": []}}}
    after = {"prometheus_available": True, "sections": {"overview": {"qps": [{"value": [0, "2"]}]}}}
    snapshotter = FakeSnapshotter([before, after])
    store, orchestrator, _, dataset_id = build(snapshotter=snapshotter)

    benchmark = fetch(
        store, run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])["benchmark_id"]
    )

    assert benchmark["operational_metrics"] == {"before": before, "after": after}
    assert snapshotter.calls == 2


def test_prometheus_evidence_groups_llm_metrics_by_bounded_dimensions():
    pipeline = SNAPSHOT_QUERIES["pipeline"]

    for name in (
        "llm_p50_by_request_type",
        "llm_p95_by_request_type",
        "llm_provider_p95_by_request_type",
        "llm_wall_time_rate",
        "llm_request_rate",
        "llm_error_rate",
        "llm_input_token_rate",
        "llm_output_token_rate",
        "llm_total_token_rate",
        "llm_finish_reason_rate",
        "llm_output_tokens_p50_by_request_type",
        "llm_output_tokens_p95_by_request_type",
        "llm_output_tokens_p99_by_request_type",
    ):
        assert "request_type" in pipeline[name]
        assert "traffic_class" in pipeline[name]
        assert not any(
            forbidden in pipeline[name]
            for forbidden in (
                "request_id",
                "trace_id",
                "conversation_id",
                "item_id",
                "prompt",
            )
        )

    assert "finish_reason" in pipeline["llm_finish_reason_rate"]
    assert "histogram_quantile(0.50" in pipeline["llm_p50_by_request_type"]
    assert "ragapp_llm_request_duration_seconds_bucket" in pipeline["llm_p50_by_request_type"]
    assert "le" in pipeline["llm_p50_by_request_type"]
    for name, quantile in (
        ("llm_output_tokens_p50_by_request_type", "0.50"),
        ("llm_output_tokens_p95_by_request_type", "0.95"),
        ("llm_output_tokens_p99_by_request_type", "0.99"),
    ):
        assert f"histogram_quantile({quantile}" in pipeline[name]
        assert "ragapp_llm_output_tokens_bucket" in pipeline[name]
        assert "le" in pipeline[name]


def test_a_snapshot_outage_does_not_fail_the_benchmark():
    unavailable = {"prometheus_available": False, "sections": {}}
    store, orchestrator, _, dataset_id = build(
        snapshotter=FakeSnapshotter([unavailable, unavailable])
    )

    benchmark = fetch(
        store, run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])["benchmark_id"]
    )

    assert benchmark["status"] == BENCHMARK_COMPLETED
    assert benchmark["operational_metrics"]["before"]["prometheus_available"] is False
    assert benchmark["operational_metrics"]["after"]["prometheus_available"] is False

