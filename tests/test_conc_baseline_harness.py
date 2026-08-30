"""Focused regression for the CONC-00 measurement harness.

Deterministic and offline by design. The harness's whole value is that the
numbers in an artifact come from logic that was tested, so these exercise the
driver with in-process fakes rather than a Compose stack — the same code path
that later runs against live services.
"""
import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from perf import artifact as artifact_module  # noqa: E402
from perf import drivers, harness, scenarios, stats  # noqa: E402
from perf.harness import CallResult  # noqa: E402


# ── statistics ──────────────────────────────────────────────


def test_percentiles_return_observed_samples_not_interpolations():
    samples = [float(n) for n in range(1, 101)]
    summary = stats.LatencySummary.from_samples(samples)

    assert summary.p50 == 50.0
    assert summary.p95 == 95.0
    assert summary.p99 == 99.0
    assert summary.minimum == 1.0
    assert summary.maximum == 100.0


def test_p99_is_withheld_below_the_sample_floor():
    """Under 100 samples the nearest-rank p99 is just the maximum wearing a
    statistical name, and two baselines would be comparing outliers."""
    samples = [float(n) for n in range(1, 21)]
    summary = stats.LatencySummary.from_samples(samples)

    assert summary.p95 is not None
    assert summary.p99 is None
    assert stats.latency_limitations(samples), "the withheld p99 must be explained"


def test_empty_samples_summarize_to_null_rather_than_zero():
    summary = stats.LatencySummary.from_samples([])

    assert summary.count == 0
    assert summary.p50 is None and summary.mean is None and summary.maximum is None


def test_throughput_counts_completions_not_attempts():
    outcomes = stats.OutcomeCounts()
    for outcome in ("success", "success", "fallback", "error", "timeout"):
        outcomes.record(outcome)

    # 3 answers in 2 seconds — the two failures never completed.
    assert outcomes.completed == 3
    assert stats.achieved_throughput(outcomes.completed, 2.0) == pytest.approx(1.5)


def test_throughput_is_null_when_the_clock_is_unusable():
    assert stats.achieved_throughput(5, 0.0) is None


def test_unknown_outcome_names_are_rejected():
    with pytest.raises(ValueError):
        stats.OutcomeCounts().record("degraded")


# ── the load driver ─────────────────────────────────────────


def test_profile_never_exceeds_its_nominal_concurrency():
    """A driver that overshoots reports latency for a load nobody asked for."""
    peak = 0
    in_flight = 0

    async def call(index):
        nonlocal peak, in_flight
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.001)
        in_flight -= 1
        return CallResult(outcome="success", latency_seconds=0.001)

    profile = asyncio.run(
        harness.run_profile(call, concurrency=4, total_requests=40, sample_resources=False)
    )

    assert peak <= 4
    assert profile["requests"] == 40
    assert profile["outcomes"]["success"] == 40


def test_warmup_calls_are_driven_but_excluded_from_the_measurement():
    seen = []

    async def call(index):
        seen.append(index)
        return CallResult(outcome="success", latency_seconds=0.01)

    profile = asyncio.run(
        harness.run_profile(
            call,
            concurrency=2,
            total_requests=6,
            warmup_requests=3,
            sample_resources=False,
        )
    )

    assert len(seen) == 9, "warmup must actually run"
    assert profile["requests"] == 6, "warmup must not be counted"
    assert profile["warmup_requests"] == 3


def test_a_raising_call_is_counted_not_propagated():
    """A load driver that dies on the first failure measures nothing about a
    system under stress, which is the only state worth measuring."""

    async def call(index):
        if index % 2:
            raise RuntimeError("downstream refused the connection")
        return CallResult(outcome="success", latency_seconds=0.01)

    profile = asyncio.run(
        harness.run_profile(call, concurrency=2, total_requests=10, sample_resources=False)
    )

    assert profile["outcomes"]["error"] == 5
    assert profile["outcomes"]["success"] == 5


def test_a_call_over_the_ceiling_is_a_timeout_not_an_error():
    async def call(index):
        await asyncio.sleep(1.0)
        return CallResult(outcome="success", latency_seconds=1.0)

    profile = asyncio.run(
        harness.run_profile(
            call,
            concurrency=2,
            total_requests=2,
            call_timeout_seconds=0.02,
            sample_resources=False,
        )
    )

    assert profile["outcomes"]["timeout"] == 2
    assert profile["outcomes"]["error"] == 0


def test_timeouts_are_excluded_from_the_latency_distribution():
    """A timeout's latency is the ceiling by construction, so including it
    would report the harness's own setting as the system's p95."""

    async def call(index):
        if index == 0:
            return CallResult(outcome="success", latency_seconds=0.01)
        return CallResult(outcome="timeout", latency_seconds=120.0)

    profile = asyncio.run(
        harness.run_profile(call, concurrency=1, total_requests=2, sample_resources=False)
    )

    assert profile["latency"]["count"] == 1
    assert profile["latency"]["max_seconds"] == pytest.approx(0.01)


def test_fallbacks_are_counted_separately_from_successes():
    async def call(index):
        return CallResult(outcome="fallback", latency_seconds=0.01)

    profile = asyncio.run(
        harness.run_profile(call, concurrency=2, total_requests=4, sample_resources=False)
    )

    assert profile["outcomes"]["fallback"] == 4
    assert profile["outcomes"]["success"] == 0
    # A degraded answer is still an answer, so it counts toward throughput.
    assert profile["achieved_throughput_per_second"] is not None


def test_the_ladder_runs_every_configured_concurrency_point():
    async def call(index):
        return CallResult(outcome="success", latency_seconds=0.001)

    profiles = asyncio.run(
        harness.run_ladder(
            call,
            concurrency_ladder=(1, 4, 8),
            requests_per_profile=4,
            warmup_requests=0,
        )
    )

    assert [p["concurrency"] for p in profiles] == [1, 4, 8]


def test_a_saturated_ladder_stops_short_and_says_so():
    """CONC-00 asks for evidence, not for an OOM'd accelerator."""

    async def call(index):
        return CallResult(outcome="success", latency_seconds=0.001)

    profiles = asyncio.run(
        harness.run_ladder(
            call,
            concurrency_ladder=(1, 4, 8, 16, 32),
            requests_per_profile=2,
            warmup_requests=0,
            stop_on_saturation=lambda profile: profile["concurrency"] >= 4,
        )
    )

    assert [p["concurrency"] for p in profiles] == [1, 4]
    assert any("saturated" in note for note in profiles[-1]["limitations"])


def test_concurrency_below_one_is_rejected():
    async def call(index):
        return CallResult(outcome="success", latency_seconds=0.0)

    with pytest.raises(ValueError):
        asyncio.run(harness.run_profile(call, concurrency=0, total_requests=1))


# ── response classification ─────────────────────────────────


def test_a_plain_2xx_without_a_classifier_is_a_success():
    assert drivers.classify_response(200, {"response": "hi"}) == "success"


def test_a_rag_turn_that_came_back_without_rag_is_a_fallback():
    spec = scenarios.SCENARIOS_BY_NAME["gateway_chat_rag"]
    assert drivers.classify_response(200, {"use_rag": False}, spec.classify) == "fallback"
    assert drivers.classify_response(200, {"use_rag": True}, spec.classify) == "success"


def test_extended_retrieval_with_no_sources_is_a_fallback():
    spec = scenarios.SCENARIOS_BY_NAME["rag_extended"]
    assert drivers.classify_response(200, {"use_rag": True, "sources": []}, spec.classify) == "fallback"
    assert drivers.classify_response(200, {"use_rag": True, "sources": [{"id": "c1"}]}, spec.classify) == "success"


@pytest.mark.parametrize("status_code", [408, 504])
def test_server_side_expiry_statuses_are_timeouts(status_code):
    assert drivers.classify_response(status_code, None) == "timeout"


@pytest.mark.parametrize("status_code", [401, 429, 500, 503])
def test_other_failures_are_errors(status_code):
    assert drivers.classify_response(status_code, None) == "error"


def test_csrf_header_is_sent_on_unsafe_methods_only():
    class FakeCookies(dict):
        def get(self, name, default=None):
            return dict.get(self, name, default)

    class FakeClient:
        cookies = FakeCookies({drivers.DEFAULT_CSRF_COOKIE: "csrf-value"})

    session = drivers.GatewaySession(FakeClient())
    assert session.headers("POST") == {"x-csrf-token": "csrf-value"}
    assert session.headers("GET") == {}


def test_scenario_payloads_are_deterministic_per_index():
    """Two baseline runs must send byte-identical work, or they are not
    comparable."""
    spec = scenarios.SCENARIOS_BY_NAME["gateway_chat_plain"]
    assert spec.http.body(7) == spec.http.body(7)
    assert spec.http.body(7) != spec.http.body(8)


# ── the artifact ────────────────────────────────────────────


def test_every_request_class_the_task_names_is_declared():
    from shared.metrics import CONCURRENCY_REQUEST_CLASSES

    assert {spec.name for spec in scenarios.SCENARIOS} == CONCURRENCY_REQUEST_CLASSES


def test_an_unmeasured_class_must_state_why():
    """Omission is what lets a reader mistake 'never measured' for 'fine'."""
    spec = scenarios.SCENARIOS_BY_NAME["memory_operation"]
    with pytest.raises(ValueError):
        artifact_module.scenario_result(spec, profiles=[])


def test_a_deferred_class_appears_in_the_artifact_with_its_reason():
    spec = scenarios.SCENARIOS_BY_NAME["embedding_query"]
    entry = artifact_module.scenario_result(spec)

    assert entry["status"] == artifact_module.STATUS_DEFERRED
    assert entry["profiles"] == []
    assert "RabbitMQ RPC" in entry["deferred_reason"]


def test_the_artifact_lists_deferred_classes_in_its_limitations():
    entries = [
        artifact_module.scenario_result(scenarios.SCENARIOS_BY_NAME["embedding_query"]),
        artifact_module.scenario_result(
            scenarios.SCENARIOS_BY_NAME["memory_operation"],
            profiles=[{"concurrency": 1, "requests": 1}],
        ),
    ]
    document = artifact_module.build_artifact(
        entries,
        concurrency_ladder=[1, 4],
        requests_per_profile=10,
        warmup_requests=1,
        call_timeout_seconds=30.0,
    )

    assert document["artifact"] == artifact_module.ARTIFACT_KIND
    assert document["schema_version"] == artifact_module.ARTIFACT_SCHEMA_VERSION
    assert any("embedding_query" in note for note in document["limitations"])


def test_the_config_snapshot_carries_no_secret_shaped_names():
    from perf.runtime import CONFIG_ALLOWLIST, _is_secret_shaped

    for name in CONFIG_ALLOWLIST:
        assert not _is_secret_shaped(name), name


def test_the_secret_guard_catches_credentials_without_rejecting_token_budgets():
    """`TOKEN` is a credential; `..._BATCHED_TOKENS` is a scheduler budget and
    one of the knobs this whole track moves."""
    from perf.runtime import _is_secret_shaped

    assert _is_secret_shaped("HF_TOKEN")
    assert _is_secret_shaped("INTERNAL_AUTH_SECRET")
    assert _is_secret_shaped("QDRANT_API_KEY")
    assert not _is_secret_shaped("VLLM_MAX_NUM_BATCHED_TOKENS")


def test_the_artifact_round_trips_as_json(tmp_path):
    document = artifact_module.build_artifact(
        [artifact_module.scenario_result(scenarios.SCENARIOS_BY_NAME["embedding_query"])],
        concurrency_ladder=list(harness.DEFAULT_CONCURRENCY_LADDER),
        requests_per_profile=100,
        warmup_requests=10,
        call_timeout_seconds=120.0,
    )
    path = artifact_module.write_artifact(document, tmp_path / "baseline.json")

    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["load"]["concurrency_ladder"] == [1, 4, 8, 16, 32]
    assert reloaded["source"].keys() == {"git_sha", "git_branch", "dirty"}


def test_the_required_concurrency_ladder_is_the_default():
    assert harness.DEFAULT_CONCURRENCY_LADDER == (1, 4, 8, 16, 32)


# ── the CLI's degraded mode ─────────────────────────────────


def test_a_run_with_no_stack_still_writes_a_complete_artifact(tmp_path):
    """Docker being stopped must degrade the artifact, not prevent one."""
    from perf import run_baseline

    exit_code = run_baseline.main(
        ["--out-dir", str(tmp_path), "--requests", "1", "--warmup", "0"]
    )
    assert exit_code == 0

    written = list(tmp_path.glob("conc_baseline_*.json"))
    assert len(written) == 1
    document = json.loads(written[0].read_text(encoding="utf-8"))

    assert {entry["name"] for entry in document["scenarios"]} == {
        spec.name for spec in scenarios.SCENARIOS
    }
    assert all(entry["status"] == artifact_module.STATUS_DEFERRED for entry in document["scenarios"])
    assert all(entry["deferred_reason"] for entry in document["scenarios"])


def test_require_live_fails_the_run_when_a_class_was_deferred(tmp_path):
    from perf import run_baseline

    assert run_baseline.main(
        ["--out-dir", str(tmp_path), "--requests", "1", "--warmup", "0", "--require-live"]
    ) == 1


def test_writes_are_skipped_unless_the_operator_opts_in():
    from perf import run_baseline

    spec = scenarios.SCENARIOS_BY_NAME["file_ingestion"]
    assert spec.mutates_state
    reason = run_baseline._skip_reason(spec, "http://gateway", include_writes=False)
    assert reason and "--include-writes" in reason
    assert run_baseline._skip_reason(spec, "http://gateway", include_writes=True) is None


# ── the service-side probes ─────────────────────────────────


def test_a_raising_handler_still_releases_the_inflight_gauge():
    """A gauge that only counts successful exits drifts upward forever and
    reads as permanent saturation."""
    pytest.importorskip("prometheus_client")
    from shared.concurrency_probe import track_inflight
    from shared.metrics import METRICS

    gauge = METRICS.inflight_by_stage.labels(service="test", stage="gateway_chat_plain")
    before = gauge._value.get()

    with pytest.raises(RuntimeError):
        with track_inflight("test", "gateway_chat_plain"):
            raise RuntimeError("handler blew up")

    assert gauge._value.get() == before


def test_queue_wait_is_not_recorded_when_the_caller_did_not_measure_it():
    """'Started immediately' and 'we never looked' must not be the same series."""
    pytest.importorskip("prometheus_client")
    from shared.concurrency_probe import track_stage
    from shared.metrics import METRICS

    wait = METRICS.queue_wait_seconds.labels(service="test", stage="rag_extended")
    before = wait._sum.get()

    with track_stage("test", "rag_extended", accepted_at=None):
        pass

    assert wait._sum.get() == before


def test_a_thread_pool_snapshot_reports_its_ceiling_and_idle_workers():
    pytest.importorskip("prometheus_client")
    from shared.concurrency_probe import snapshot_thread_pool

    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(lambda n: n, range(3)))
        snapshot = snapshot_thread_pool("test", "default", executor)

    assert snapshot.max_workers == 3
    assert snapshot.queued == 0
    assert snapshot.active is not None and 0 <= snapshot.active <= 3


def test_a_pool_without_the_expected_internals_degrades_to_null():
    """A CPython change must not raise into a request path."""
    from shared.concurrency_probe import read_thread_pool

    class OpaquePool:
        _max_workers = 4

    snapshot = read_thread_pool(OpaquePool())  # type: ignore[arg-type]
    assert snapshot.max_workers == 4
    assert snapshot.active is None and snapshot.queued is None


def test_the_loop_sampler_measures_lag_and_stops_cleanly():
    pytest.importorskip("prometheus_client")
    from shared.concurrency_probe import EventLoopLagSampler

    async def exercise():
        sampler = EventLoopLagSampler("test", interval=0.001)
        lag = await sampler.sample_once()
        sampler.start()
        assert sampler.running
        await sampler.stop()
        assert not sampler.running
        return lag

    assert asyncio.run(exercise()) >= 0.0
