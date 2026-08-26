"""Tests for the diagnostic benchmark orchestrator.

Every phase here is driven through the real :class:`EvalRunner` over fake
transports, because the point of the orchestrator is that a phase is an
ordinary eval run. A double standing in for the runner would let this suite
pass while the two produced different numbers.

Async tests are written as sync functions driving ``asyncio.run``, matching
``test_eval_runner.py``. That keeps the suite independent of pytest-asyncio.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from app.services.benchmark_prometheus import SNAPSHOT_QUERIES
from app.services.benchmark_runner import (
    BENCHMARK_ACTIONS,
    GET_BENCHMARK_RUN,
    PHASE_COMPLETED,
    PHASE_END_TO_END_EXTENDED,
    PHASE_END_TO_END_REGULAR,
    PHASE_FAILED,
    PHASE_INTERRUPTED,
    PHASE_NAMES,
    PHASE_PARTIAL,
    PHASE_QUEUED,
    PHASE_RETRIEVAL_BASE,
    PHASE_RETRIEVAL_EXTENDED,
    PHASE_SKIPPED,
    PHASE_UNSUPPORTED,
    START_BENCHMARK_RUN,
    BenchmarkRunner,
    _phase_item_count,
    benchmark_status,
    plan_phases,
)
from app.services.eval_runner import (
    MODE_END_TO_END,
    MODE_RETRIEVAL,
    PIPELINE_EXTENDED,
    PIPELINE_REGULAR,
    EvalRunner,
)
from app.services.eval_store import (
    BENCHMARK_COMPLETED,
    BENCHMARK_FAILED,
    BENCHMARK_INTERRUPTED,
    BENCHMARK_PARTIAL,
    BENCHMARK_QUEUED,
    EvalNotFound,
    EvalStore,
    EvalValidationError,
    canonical_items,
    dataset_fingerprint,
)
from shared.auth import AuthIdentity
from shared.context import bound_context

ADMIN = AuthIdentity(tenant_id="tenant-a", user_id="admin-a", role="admin", admin_id="admin-a")

ITEMS = [
    {"query": "first", "relevant_chunk_ids": ["c1"]},
    {"query": "third", "relevant_chunk_ids": ["c9"]},
]

RESPONSES = {
    "first": {"chunks": [{"chunk_id": "c1"}, {"chunk_id": "c2"}, {"chunk_id": "c3"}]},
    "third": {"chunks": [{"chunk_id": "c1"}, {"chunk_id": "c2"}, {"chunk_id": "c9"}]},
}

GRAPH_RESULTS = {
    "first": {
        "answer": "Alpha is first [1].",
        "sources": [{"chunk_id": "c1"}],
        "review": {"groundedness_score": 0.9, "hallucination_verdict": "none"},
        "citation_metrics": {"citation_precision": 1.0, "citation_recall": 1.0},
    },
    "third": {
        "answer": "Gamma is ninth [1].",
        "sources": [{"chunk_id": "c9"}],
        "review": {"groundedness_score": 0.8, "hallucination_verdict": "none"},
        "citation_metrics": {"citation_precision": 1.0, "citation_recall": 1.0},
    },
}


def build_config(**overrides: Any) -> SimpleNamespace:
    settings: Dict[str, Any] = {
        "conversation_store_type": "in_memory",
        "eval_datasets_collection": "eval_datasets",
        "eval_runs_collection": "eval_runs",
        "eval_benchmark_runs_collection": "eval_benchmark_runs",
        "eval_max_dataset_items": 1000,
        "eval_max_query_length": 2000,
        "eval_lease_seconds": 300,
        "eval_run_concurrency": 4,
        "eval_candidate_k": 20,
        "eval_validate_labels": True,
        "eval_stale_label_policy": "fail",
        "eval_max_reported_stale_ids": 50,
        "mongodb_url": "mongodb://localhost:27017/",
        "mongodb_database": "rag",
        "mongodb_max_retries": 1,
        "mongodb_retry_delay": 0,
        "top_k_documents": 6,
        "reranker_enabled": True,
        "reranker_top_k": 5,
        "hybrid_search_enabled": True,
        "hybrid_search_alpha": 0.55,
        "min_similarity_threshold": 0.4,
    }
    settings.update(overrides)
    return SimpleNamespace(**settings)


class FakeBackend:
    """Answer retrieval and label verification from tables."""

    def __init__(
        self,
        *,
        fail_queries: Optional[set] = None,
        block: Optional[asyncio.Event] = None,
    ) -> None:
        self.fail_queries = fail_queries or set()
        self.block = block
        self.calls: List[Dict[str, Any]] = []

    async def verify_label_ids(self, request, chunk_ids=None, file_ids=None):
        def report(values):
            return {
                "present": sorted(values),
                "retrievable": sorted(values),
                "missing": [],
            }

        return {"chunk_ids": report(chunk_ids or []), "file_ids": report(file_ids or [])}

    async def search_chunks(
        self, request, query, retrieval_plan=None, pass_name="pass_one", *, top_k=None
    ):
        self.calls.append({"query": query, "pipeline_mode": request.mode})
        if self.block is not None:
            await self.block.wait()
        await asyncio.sleep(0)
        if query in self.fail_queries:
            raise RuntimeError(f"embedding unavailable for {query!r}")
        return RESPONSES.get(query, {"chunks": []})


class FakeGraphRunner:
    """Return a canned graph result, recording the pipeline mode it was asked for."""

    def __init__(self, fail_queries: Optional[set] = None) -> None:
        self.fail_queries = fail_queries or set()
        self.calls: List[Dict[str, Any]] = []

    async def run(
        self, request, emitter, resume=False, record_metrics=True, retrieval_trace=None
    ):
        self.calls.append(
            {"query": request.user_message, "pipeline_mode": request.mode}
        )
        await asyncio.sleep(0)
        if request.user_message in self.fail_queries:
            raise RuntimeError("generation unavailable")
        return GRAPH_RESULTS.get(request.user_message, {})


def build(
    *,
    graph: Any = None,
    backend: Optional[FakeBackend] = None,
    items=ITEMS,
    snapshotter: Any = None,
):
    """A store with one dataset, an eval runner, and an orchestrator over it."""
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = backend if backend is not None else FakeBackend()
    eval_runner = EvalRunner(config, store, backend, graph_runner=graph)  # type: ignore[arg-type]
    orchestrator = BenchmarkRunner(  # type: ignore[arg-type]
        config, store, eval_runner, snapshotter=snapshotter
    )
    with bound_context(**ADMIN.to_dict()):
        dataset = store.create_dataset("Golden set", None, items)
    return store, orchestrator, backend, dataset["dataset_id"]


def run_benchmark(
    orchestrator: BenchmarkRunner,
    dataset_id: str,
    phases: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Start a benchmark and wait for its background task to finish."""

    async def _go():
        benchmark = await orchestrator.start_benchmark(dataset_id, phases)
        await asyncio.gather(*list(orchestrator._tasks))
        return benchmark

    with bound_context(**ADMIN.to_dict()):
        return asyncio.run(_go())


def fetch(store: EvalStore, benchmark_id: str) -> Dict[str, Any]:
    with bound_context(**ADMIN.to_dict()):
        return store.get_benchmark_run(benchmark_id)


def phases_by_name(benchmark: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {phase["name"]: phase for phase in benchmark["phases"]}


# ── The phase plan ────────────────────────────────────────────────────────

def test_phases_run_cheapest_first():
    """A free phase that fails must report before an expensive one spends."""
    plan = plan_phases(None, graph_available=True)

    assert [phase["name"] for phase in plan] == list(PHASE_NAMES)
    assert plan[0]["name"] == PHASE_RETRIEVAL_BASE
    assert plan[0]["evaluation_mode"] == MODE_RETRIEVAL


def test_the_requested_order_does_not_override_the_cost_order():
    plan = plan_phases(
        [PHASE_END_TO_END_REGULAR, PHASE_RETRIEVAL_BASE], graph_available=True
    )

    assert [phase["name"] for phase in plan] == [
        PHASE_RETRIEVAL_BASE,
        PHASE_END_TO_END_REGULAR,
    ]


def test_extended_retrieval_is_unsupported_rather_than_faked():
    """It would report the base numbers under an extended label."""
    plan = phases_by_name({"phases": plan_phases(None, graph_available=True)})

    assert plan[PHASE_RETRIEVAL_EXTENDED]["status"] == PHASE_UNSUPPORTED
    assert "end_to_end_extended" in plan[PHASE_RETRIEVAL_EXTENDED]["reason"]


def test_answer_phases_are_unsupported_without_a_graph():
    """Blank answer-quality columns would look like a measured zero."""
    plan = phases_by_name({"phases": plan_phases(None, graph_available=False)})

    assert plan[PHASE_END_TO_END_REGULAR]["status"] == PHASE_UNSUPPORTED
    assert plan[PHASE_END_TO_END_EXTENDED]["status"] == PHASE_UNSUPPORTED
    assert plan[PHASE_RETRIEVAL_BASE]["status"] == PHASE_QUEUED


def test_a_selection_nothing_can_run_is_refused():
    with pytest.raises(EvalValidationError):
        plan_phases([PHASE_END_TO_END_REGULAR], graph_available=False)


def test_an_unknown_phase_is_refused():
    with pytest.raises(EvalValidationError):
        plan_phases(["retrieval_turbo"], graph_available=True)


# ── Evaluation mode is not pipeline mode ──────────────────────────────────

def test_each_phase_records_both_modes_separately():
    """A phase is a point in the grid, not a value in one enumeration."""
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)

    assert plan[PHASE_RETRIEVAL_BASE]["evaluation_mode"] == MODE_RETRIEVAL
    # A retrieval phase drives no pipeline, and says so rather than claiming
    # the default one.
    assert plan[PHASE_RETRIEVAL_BASE]["pipeline_mode"] is None
    assert plan[PHASE_END_TO_END_REGULAR]["evaluation_mode"] == MODE_END_TO_END
    assert plan[PHASE_END_TO_END_REGULAR]["pipeline_mode"] == PIPELINE_REGULAR
    assert plan[PHASE_END_TO_END_EXTENDED]["evaluation_mode"] == MODE_END_TO_END
    assert plan[PHASE_END_TO_END_EXTENDED]["pipeline_mode"] == PIPELINE_EXTENDED


def test_the_pipeline_mode_reaches_the_graph():
    """The extended phase must actually drive the extended pipeline."""
    graph = FakeGraphRunner()
    store, orchestrator, _, dataset_id = build(graph=graph)

    run_benchmark(orchestrator, dataset_id)

    assert {call["pipeline_mode"] for call in graph.calls} == {
        PIPELINE_REGULAR,
        PIPELINE_EXTENDED,
    }


def test_each_phase_run_carries_both_modes_and_its_benchmark():
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)
    with bound_context(**ADMIN.to_dict()):
        run = store.get_run(plan[PHASE_END_TO_END_EXTENDED]["run_id"])

    assert run["mode"] == MODE_END_TO_END
    assert run["pipeline_mode"] == PIPELINE_EXTENDED
    assert run["config_snapshot"]["pipeline_mode"] == PIPELINE_EXTENDED
    assert run["benchmark_id"] == benchmark["benchmark_id"]


# ── Progress ──────────────────────────────────────────────────────────────

def test_a_benchmark_captures_only_its_immutable_canonical_scoring_snapshot():
    store, orchestrator, _, dataset_id = build(
        items=[
            {
                "item_id": "authoring-id",
                "query": "first",
                "relevant_chunk_ids": ["c1"],
                "notes": "private annotation",
                "created_by": "admin-a",
            }
        ]
    )

    benchmark = fetch(
        store,
        run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])["benchmark_id"],
    )
    snapshot = benchmark["dataset_snapshot"]

    assert snapshot["dataset_id"] == dataset_id
    assert snapshot["dataset_version"] == benchmark["dataset_version"]
    assert snapshot["dataset_sha256"] == benchmark["dataset_sha256"]
    assert dataset_fingerprint(snapshot["items"]) == snapshot["dataset_sha256"]
    # The snapshot is the canonical scoring form of the stored dataset — the
    # items as they were normalized at import, which is what the run scored.
    with bound_context(**ADMIN.to_dict()):
        stored = store.get_dataset(dataset_id)["items"]
    assert canonical_items(snapshot["items"]) == canonical_items(stored)
    # The phase executes this snapshot, so item identity has to survive it;
    # the fingerprint assertion above proves it stays outside the hash.
    assert snapshot["items"][0]["item_id"] == stored[0]["item_id"]
    assert "notes" not in snapshot["items"][0]
    assert "created_by" not in snapshot["items"][0]


def test_benchmark_phase_rows_keep_the_item_identity_they_were_scored_under():
    """The snapshot a phase executes must not erase per-item identity.

    Rows are the only per-item evidence a drill-down or export has, and an
    ``item_id`` shared by every row cannot be joined back to a golden set
    item. The unscorable lookup is keyed by the same field, so one blank id
    would also let a single stale label mark the whole phase unscorable.
    """
    store, orchestrator, _, dataset_id = build()

    benchmark = fetch(
        store,
        run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])["benchmark_id"],
    )
    with bound_context(**ADMIN.to_dict()):
        dataset_ids = {item["item_id"] for item in store.get_dataset(dataset_id)["items"]}
        run = store.get_run(str(benchmark["phases"][0]["run_id"]))

    scored_ids = [row.get("item_id") for row in run["per_item"]]
    assert len(set(scored_ids)) == len(scored_ids)
    assert set(scored_ids) == dataset_ids


def test_a_benchmark_returns_immediately_in_queued_state():
    """A synchronous orchestration would blow the gateway timeout."""
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    async def _go():
        benchmark = await orchestrator.start_benchmark(dataset_id)
        assert benchmark["status"] == BENCHMARK_QUEUED
        assert benchmark["started_at"] is None
        await asyncio.gather(*list(orchestrator._tasks))

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_running_phase_persists_truthful_item_progress_without_poll_writes():
    blocker = asyncio.Event()
    store, orchestrator, _, dataset_id = build(backend=FakeBackend(block=blocker))

    async def _go():
        benchmark = await orchestrator.start_benchmark(dataset_id, [PHASE_RETRIEVAL_BASE])
        for _ in range(20):
            await asyncio.sleep(0)
            progress = fetch(store, benchmark["benchmark_id"])["progress"]
            if progress["current_phase"] == PHASE_RETRIEVAL_BASE:
                break
        else:
            raise AssertionError("benchmark did not enter its retrieval phase")

        before = fetch(store, benchmark["benchmark_id"])["progress"]
        again = fetch(store, benchmark["benchmark_id"])["progress"]
        assert before == again  # reads never manufacture progress
        assert before["items_completed"] == 0
        assert before["items_in_flight"] == len(ITEMS)
        assert before["phase_started_at"]
        assert before["last_progress_at"]

        blocker.set()
        await asyncio.gather(*list(orchestrator._tasks))
        return fetch(store, benchmark["benchmark_id"])

    with bound_context(**ADMIN.to_dict()):
        completed = asyncio.run(_go())

    progress = completed["progress"]
    assert progress["items_completed"] == len(ITEMS)
    assert progress["items_in_flight"] == 0
    assert progress["items_succeeded"] == len(ITEMS)
    assert (
        progress["items_succeeded"]
        + progress["items_guardrail_blocked"]
        + progress["items_failed"]
        + progress["items_timed_out"]
        == progress["items_completed"]
    )


def test_progress_counts_every_phase_and_only_the_reachable_items():
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    progress = benchmark["progress"]

    assert progress["total_phases"] == len(PHASE_NAMES)
    assert progress["executable_phases"] == 3
    assert progress["unsupported_phases"] == 1
    assert progress["completed_phases"] == 3
    assert progress["current_phase"] is None
    assert progress["items_per_phase"] == 2
    # Three executable phases over two items: the unsupported one is not a
    # denominator anybody can reach.
    assert progress["items_total"] == 6
    assert progress["items_completed"] == 6


def test_every_supported_phase_produces_its_own_run():
    store, orchestrator, _, dataset_id = build(graph=FakeGraphRunner())

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)
    run_ids = [
        plan[name]["run_id"]
        for name in (
            PHASE_RETRIEVAL_BASE,
            PHASE_END_TO_END_REGULAR,
            PHASE_END_TO_END_EXTENDED,
        )
    ]

    assert benchmark["status"] == BENCHMARK_COMPLETED
    assert all(run_ids)
    assert len(set(run_ids)) == 3
    assert plan[PHASE_RETRIEVAL_EXTENDED]["run_id"] is None
    assert plan[PHASE_RETRIEVAL_BASE]["results"]["items_evaluated"] == 2


def test_legacy_phase_item_count_does_not_add_scoring_and_execution_axes():
    phase = {
        "results": {
            "items_evaluated": 24,
            "items_skipped": 6,
            "items_unscorable": 0,
            "items_guardrail_blocked": 2,
            "items_failed": 0,
        }
    }

    assert _phase_item_count(phase) == 30


def test_a_benchmark_is_listed_and_fetched_within_its_tenant():
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    with bound_context(**ADMIN.to_dict()):
        listed = store.list_benchmark_runs(dataset_id)
    other = AuthIdentity(
        tenant_id="tenant-b", user_id="admin-b", role="admin", admin_id="admin-b"
    )

    assert [row["benchmark_id"] for row in listed] == [benchmark["benchmark_id"]]
    with bound_context(**other.to_dict()):
        assert store.list_benchmark_runs(dataset_id) == []


# ── Partial and failed ────────────────────────────────────────────────────

def test_item_failures_make_a_phase_partial_not_failed():
    """One bad query is a smaller denominator, not a lost phase."""
    backend = FakeBackend(fail_queries={"third"})
    store, orchestrator, _, dataset_id = build(backend=backend)

    benchmark = fetch(
        store,
        run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])["benchmark_id"],
    )
    phase = phases_by_name(benchmark)[PHASE_RETRIEVAL_BASE]

    assert phase["status"] == PHASE_PARTIAL
    assert phase["results"]["items_failed"] == 1
    assert phase["results"]["items_evaluated"] == 1
    assert benchmark["status"] == BENCHMARK_PARTIAL
    assert benchmark["progress"]["partial_phases"] == 1


def test_a_partial_phase_does_not_stop_the_rest():
    backend = FakeBackend(fail_queries={"third"})
    store, orchestrator, _, dataset_id = build(
        graph=FakeGraphRunner(), backend=backend
    )

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)

    assert plan[PHASE_RETRIEVAL_BASE]["status"] == PHASE_PARTIAL
    assert plan[PHASE_END_TO_END_REGULAR]["status"] == PHASE_COMPLETED
    assert plan[PHASE_END_TO_END_EXTENDED]["status"] == PHASE_COMPLETED
    assert benchmark["status"] == BENCHMARK_PARTIAL


def test_a_systemic_failure_skips_the_phases_behind_it():
    """Whatever broke the free phase breaks the expensive ones too."""
    backend = FakeBackend(fail_queries={"first", "third"})
    store, orchestrator, _, dataset_id = build(
        graph=FakeGraphRunner(), backend=backend
    )

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)

    assert plan[PHASE_RETRIEVAL_BASE]["status"] == PHASE_FAILED
    assert plan[PHASE_END_TO_END_REGULAR]["status"] == PHASE_SKIPPED
    assert plan[PHASE_END_TO_END_EXTENDED]["status"] == PHASE_SKIPPED
    assert PHASE_RETRIEVAL_BASE in plan[PHASE_END_TO_END_REGULAR]["reason"]
    # Nothing produced evidence, so the benchmark failed outright.
    assert benchmark["status"] == BENCHMARK_FAILED
    assert benchmark["error"]


def test_a_later_phase_failing_leaves_the_earlier_evidence_standing():
    store, orchestrator, _, dataset_id = build(
        graph=FakeGraphRunner(fail_queries={"first", "third"})
    )

    benchmark = fetch(store, run_benchmark(orchestrator, dataset_id)["benchmark_id"])
    plan = phases_by_name(benchmark)

    assert plan[PHASE_RETRIEVAL_BASE]["status"] == PHASE_COMPLETED
    assert plan[PHASE_END_TO_END_REGULAR]["status"] == PHASE_FAILED
    assert plan[PHASE_END_TO_END_EXTENDED]["status"] == PHASE_SKIPPED
    assert benchmark["status"] == BENCHMARK_PARTIAL


def test_status_is_completed_only_when_nothing_was_degraded():
    completed = [
        {"status": PHASE_COMPLETED},
        {"status": PHASE_UNSUPPORTED},
    ]
    degraded = [{"status": PHASE_COMPLETED}, {"status": PHASE_FAILED}]

    assert benchmark_status(completed) == BENCHMARK_COMPLETED
    assert benchmark_status(degraded) == BENCHMARK_PARTIAL
    assert benchmark_status([{"status": PHASE_FAILED}]) == BENCHMARK_FAILED


# ── Interruption ──────────────────────────────────────────────────────────

def test_cancelling_the_orchestration_closes_it_as_interrupted():
    """A benchmark stuck in `running` is indistinguishable from a live one."""
    store, orchestrator, backend, dataset_id = build()

    async def _go():
        blocker = asyncio.Event()
        backend.block = blocker
        benchmark = await orchestrator.start_benchmark(
            dataset_id, [PHASE_RETRIEVAL_BASE]
        )
        task = next(iter(orchestrator._tasks))
        # Let the orchestration reach the blocked retrieval before cancelling.
        for _ in range(20):
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return benchmark

    with bound_context(**ADMIN.to_dict()):
        benchmark = asyncio.run(_go())

    stored = fetch(store, benchmark["benchmark_id"])

    assert stored["status"] == BENCHMARK_INTERRUPTED
    assert stored["finished_at"] is not None
    assert phases_by_name(stored)[PHASE_RETRIEVAL_BASE]["status"] == PHASE_INTERRUPTED


# ── Dispatch ──────────────────────────────────────────────────────────────

def test_the_actions_are_dispatched_and_refusals_are_typed():
    store, orchestrator, _, dataset_id = build()

    async def _go():
        started = await orchestrator.handle(
            START_BENCHMARK_RUN, {"dataset_id": dataset_id}
        )
        await asyncio.gather(*list(orchestrator._tasks))
        fetched = await orchestrator.handle(
            GET_BENCHMARK_RUN,
            {"benchmark_id": started["benchmark"]["benchmark_id"]},
        )
        missing = await orchestrator.handle(GET_BENCHMARK_RUN, {"benchmark_id": "nope"})
        return started, fetched, missing

    with bound_context(**ADMIN.to_dict()):
        started, fetched, missing = asyncio.run(_go())

    assert START_BENCHMARK_RUN in BENCHMARK_ACTIONS
    assert fetched["benchmark"]["benchmark_id"] == started["benchmark"]["benchmark_id"]
    assert missing["eval_error"]["kind"] == "not_found"


def test_a_refused_benchmark_leaves_no_document_behind():
    """The dataset is resolved before anything is written."""
    store, orchestrator, _, _ = build()

    async def _go():
        with pytest.raises(EvalNotFound):
            await orchestrator.start_benchmark("no-such-dataset")

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())
        assert store.list_benchmark_runs() == []


def test_completed_phase_persists_explicit_wall_clock_fields():
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    phase = phases_by_name(fetch(store, benchmark["benchmark_id"]))[
        PHASE_RETRIEVAL_BASE
    ]

    assert phase["phase_started_at"] == phase["started_at"]
    assert phase["phase_finished_at"] == phase["finished_at"]
    assert phase["phase_wall_clock_ms"] >= 0


# ── Manifest ──────────────────────────────────────────────────────────────

def test_a_benchmark_records_the_manifest_it_ran_under(monkeypatch):
    """Provenance is captured automatically, not remembered by an operator."""
    monkeypatch.setenv("RAGFORGE_GIT_SHA", "abc123def456")
    monkeypatch.setenv("RAGFORGE_GIT_BRANCH", "feat/benchmark-run-manifest")
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    manifest = fetch(store, benchmark["benchmark_id"])["manifest"]

    assert manifest["build"]["git_sha"] == "abc123def456"
    assert manifest["build"]["git_branch"] == "feat/benchmark-run-manifest"
    assert manifest["dataset"]["dataset_id"] == dataset_id
    assert manifest["dataset"]["item_count"] == len(ITEMS)
    assert manifest["dataset"]["phases"] == [PHASE_RETRIEVAL_BASE]
    assert manifest["retrieval"]["top_k_documents"] == 6


def test_the_manifest_is_written_once_at_plan_time():
    """Config drifting mid-benchmark must not rewrite what the phases ran on."""
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    captured = benchmark["manifest"]["captured_at"]
    orchestrator.config.top_k_documents = 99

    stored = fetch(store, benchmark["benchmark_id"])["manifest"]
    assert stored["captured_at"] == captured
    assert stored["retrieval"]["top_k_documents"] == 6


def test_a_benchmark_recorded_before_manifests_reads_back_as_null():
    """No manifest is invented for a document that never carried one."""
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    for document in store._memory[store.config.eval_benchmark_runs_collection]:
        document.pop("manifest", None)

    with bound_context(**ADMIN.to_dict()):
        assert store.get_benchmark_run(benchmark["benchmark_id"])["manifest"] is None
        assert store.list_benchmark_runs()[0]["manifest"] is None


class FakeSnapshotter:
    def __init__(self, snapshots: List[Dict[str, Any]]) -> None:
        self.snapshots = snapshots
        self.calls = 0

    async def capture(self) -> Dict[str, Any]:
        result = self.snapshots[self.calls]
        self.calls += 1
        return result


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
        "llm_p95_by_request_type",
        "llm_provider_p95_by_request_type",
        "llm_wall_time_rate",
        "llm_request_rate",
        "llm_error_rate",
        "llm_output_token_rate",
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
