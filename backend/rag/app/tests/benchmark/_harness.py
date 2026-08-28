"""Shared benchmark-orchestrator doubles.

Every phase is driven through the real :class:`EvalRunner` over fake
transports, because the point of the orchestrator is that a phase is an
ordinary eval run. A double standing in for the runner would let the lane
pass while the two produced different numbers.

Async tests are written as sync functions driving ``asyncio.run``, keeping the
lane independent of pytest-asyncio.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional


from app.services.benchmark_runner import (
    PHASE_NAMES,
    BenchmarkRunner,
)
from app.services.eval_runner import (
    EvalRunner,
)
from app.services.retrieval_trace import STAGE_FINAL_CONTEXT
from app.services.eval_store import (
    EvalStore,
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
        result = GRAPH_RESULTS.get(request.user_message, {})
        if retrieval_trace is not None:
            # The real graph commits its terminal context at the generation
            # boundary; a fake that skipped it would leave every item without
            # the evidence the runner scores.
            retrieval_trace.record_stage(
                STAGE_FINAL_CONTEXT, result.get("sources") or []
            )
        return result


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
        requested = list(PHASE_NAMES) if phases is None else phases
        benchmark = await orchestrator.start_benchmark(dataset_id, requested)
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

class FakeSnapshotter:
    def __init__(self, snapshots: List[Dict[str, Any]]) -> None:
        self.snapshots = snapshots
        self.calls = 0

    async def capture(self) -> Dict[str, Any]:
        result = self.snapshots[self.calls]
        self.calls += 1
        return result


