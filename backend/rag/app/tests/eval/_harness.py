"""Shared eval-runner doubles: a backend returning known orderings and a fake graph.

Every expected aggregate in the eval lane is hand-computable from these
responses. Nothing here touches RabbitMQ, MongoDB or an LLM — which is also
the runner's own contract: it must never call one.

Async tests are written as sync functions driving ``asyncio.run``, keeping the
lane independent of pytest-asyncio.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional


from app.services.eval_runner import (
    MODE_END_TO_END,
    STALE_POLICY_FAIL,
    EvalRunner,
)
from app.services.eval_store import EvalStore
from shared.auth import AuthIdentity
from shared.context import bound_context
from shared.metrics import traffic_class

ADMIN = AuthIdentity(tenant_id="tenant-a", user_id="admin-a", role="admin", admin_id="admin-a")

# item-1's sole relevant chunk ranks first; item-2's ranks third.
RESPONSES = {
    "first": {"chunks": [{"chunk_id": "c1"}, {"chunk_id": "c2"}, {"chunk_id": "c3"}]},
    "third": {"chunks": [{"chunk_id": "c1"}, {"chunk_id": "c2"}, {"chunk_id": "c9"}]},
}

ITEMS = [
    {"query": "first", "relevant_chunk_ids": ["c1"]},
    {"query": "third", "relevant_chunk_ids": ["c9"]},
]


def build_config(**overrides: Any) -> SimpleNamespace:
    settings: Dict[str, Any] = {
        "conversation_store_type": "in_memory",
        "eval_datasets_collection": "eval_datasets",
        "eval_runs_collection": "eval_runs",
        "eval_max_dataset_items": 1000,
        "eval_max_query_length": 2000,
        "eval_lease_seconds": 300,
        "eval_run_concurrency": 4,
        "eval_candidate_k": 20,
        "eval_validate_labels": True,
        "eval_stale_label_policy": STALE_POLICY_FAIL,
        "eval_max_reported_stale_ids": 50,
        "mongodb_url": "mongodb://localhost:27017/",
        "mongodb_database": "rag",
        "mongodb_max_retries": 1,
        "mongodb_retry_delay": 0,
        "top_k_documents": 6,
        "reranker_enabled": True,
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "reranker_model_revision": "test-revision",
        "reranker_candidate_k": 20,
        "reranker_timeout_seconds": 0.1,
        "reranker_batch_size": 8,
        "reranker_max_length": 512,
        "hybrid_search_enabled": True,
        "hybrid_search_alpha": 0.55,
        "min_similarity_threshold": 0.4,
    }
    settings.update(overrides)
    return SimpleNamespace(**settings)


class FakeBackend:
    """Answer `search_chunks` from a table, tracking overlap and failures."""

    def __init__(
        self,
        responses: Optional[Dict[str, Any]] = None,
        *,
        fail_queries: Optional[set] = None,
        index: Optional[set] = None,
        barred: Optional[set] = None,
        verify_error: Optional[str] = None,
        resolutions: Optional[List[Dict[str, Any]]] = None,
        chunk_resolutions: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.responses = responses if responses is not None else RESPONSES
        self.fail_queries = fail_queries or set()
        self.calls: List[Dict[str, Any]] = []
        self.in_flight = 0
        self.max_in_flight = 0
        # None means "every id asked about exists" — the state a golden set
        # is in until something reindexes underneath it.
        self.index = index
        self.barred = barred or set()
        self.verify_error = verify_error
        self.verify_calls: List[Dict[str, Any]] = []
        self.resolutions = resolutions or []
        self.chunk_resolutions = chunk_resolutions

    async def resolve_file_labels(self, request, labels):
        return {"resolutions": self.resolutions}

    async def resolve_chunk_labels(self, request, items):
        if self.chunk_resolutions is not None:
            return {"resolutions": self.chunk_resolutions}
        return {
            "resolutions": [
                {
                    "item_id": item["item_id"],
                    "files": [
                        {"file_id": file_id, "status": "READY", "searchable": True}
                        for file_id in item["file_ids"]
                    ],
                    "facts": [],
                    "chunk_ids": [],
                }
                for item in items
            ]
        }

    async def verify_label_ids(self, request, chunk_ids=None, file_ids=None):
        self.verify_calls.append(
            {"chunk_ids": list(chunk_ids or []), "file_ids": list(file_ids or [])}
        )
        if self.verify_error:
            raise RuntimeError(self.verify_error)

        def report(values):
            present = {
                value for value in values if self.index is None or value in self.index
            }
            return {
                "present": sorted(present),
                "retrievable": sorted(present - self.barred),
                "missing": sorted(set(values) - present),
            }

        return {"chunk_ids": report(chunk_ids or []), "file_ids": report(file_ids or [])}

    async def search_chunks(
        self, request, query, retrieval_plan=None, pass_name="pass_one", *, top_k=None
    ):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self.calls.append(
            {
                "query": query,
                "pass_name": pass_name,
                "tenant": request.tenant_id,
                "top_k": top_k,
                "traffic_class": traffic_class(),
            }
        )
        try:
            # Yield so concurrent items genuinely overlap; without this the
            # coroutine would run to completion before the next one starts
            # and the semaphore bound would be trivially satisfied.
            await asyncio.sleep(0)
            if query in self.fail_queries:
                raise RuntimeError(f"embedding unavailable for {query!r}")
            return self.responses.get(query, {"chunks": []})
        finally:
            self.in_flight -= 1


def build(items=ITEMS, backend=None, **config_overrides):
    """Create a store with one dataset, plus a runner over a fake backend."""
    config = build_config(**config_overrides)
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = backend or FakeBackend()
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    with bound_context(**ADMIN.to_dict()):
        dataset = store.create_dataset("Golden set", None, items)
    return store, runner, backend, dataset["dataset_id"]


def execute(runner: EvalRunner, dataset_id: str) -> Dict[str, Any]:
    """Start a run and wait for its background task to finish."""

    async def _go():
        run = await runner.start_run(dataset_id)
        await asyncio.gather(*list(runner._tasks))
        return run

    with bound_context(**ADMIN.to_dict()):
        return asyncio.run(_go())


def fetch(store: EvalStore, run_id: str) -> Dict[str, Any]:
    with bound_context(**ADMIN.to_dict()):
        return store.get_run(run_id)


# ── The happy path ────────────────────────────────────────────────────────


class FakeGraphRunner:
    """Return a canned graph result per query, recording how it was called."""

    def __init__(self, results: Dict[str, Any]) -> None:
        self.results = results
        self.calls: List[Dict[str, Any]] = []

    async def run(
        self, request, emitter, resume=False, record_metrics=True, retrieval_trace=None
    ):
        self.calls.append(
            {
                "query": request.user_message,
                "record_metrics": record_metrics,
                "pipeline_mode": request.mode,
                "traced": retrieval_trace is not None,
            }
        )
        await asyncio.sleep(0)
        result = self.results.get(request.user_message, {})
        if retrieval_trace is not None and result.get("outcome", "success") == "success":
            retrieval_trace.record_stage(
                "final_context",
                result.get("sources") if isinstance(result.get("sources"), list) else [],
            )
        return result


GRAPH_RESULTS = {
    "first": {
        "answer": "Alpha is first [1].",
        "sources": [{"chunk_id": "c1"}, {"chunk_id": "c2"}],
        "review": {
            "groundedness_score": 0.9,
            "hallucination_verdict": "none",
            "unsupported_claim_count": 0,
        },
        "citation_metrics": {"citation_precision": 1.0, "citation_recall": 1.0},
    },
    "third": {
        "answer": "Gamma is ninth.",
        "sources": [{"chunk_id": "c9"}],
        "review": {
            "groundedness_score": 0.5,
            "hallucination_verdict": "severe",
            "unsupported_claim_count": 2,
        },
        # Cited nothing: precision is unmeasured, not zero.
        "citation_metrics": {"citation_precision": None, "citation_recall": 0.0},
    },
}


def run_end_to_end(runner: EvalRunner, dataset_id: str) -> Dict[str, Any]:
    async def _go():
        run = await runner.start_run(dataset_id, MODE_END_TO_END)
        await asyncio.gather(*list(runner._tasks))
        return run

    with bound_context(**ADMIN.to_dict()):
        return asyncio.run(_go())


class FailingGraph(FakeGraphRunner):
    """A graph that dies at a chosen point, reporting it the way the real one does."""

    def __init__(self, result: Dict[str, Any], *, context: Any = None) -> None:
        super().__init__({})
        self.result = result
        self.context = context

    async def run(self, request, emitter, **kwargs):
        trace = kwargs["retrieval_trace"]
        if self.context is not None:
            trace.record_stage("base", self.context)
            # Committed by the graph at the generation boundary, before the
            # node that is about to fail.
            trace.record_stage("final_context", self.context)
        await asyncio.sleep(0)
        return self.result
