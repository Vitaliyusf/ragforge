"""Tests for the eval runner: aggregate correctness, failure paths, bounds.

The backend client is a double returning known orderings, so every expected
aggregate below is hand-computable. Nothing here touches RabbitMQ, MongoDB or
an LLM — which is also the runner's own contract: it must never call one.

Async tests are written as sync functions driving ``asyncio.run``, matching
``test_rag.py``. That keeps the suite independent of pytest-asyncio.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from app.services.eval_runner import (
    MATCH_CHUNK,
    MATCH_FILE,
    MATCH_MIXED,
    EvalRunner,
    aggregate,
    dataset_match_mode,
    eligible_chunks,
    relevant_ids,
    retrieved_ids,
)
from app.services.eval_store import EvalStore, EvalValidationError
from shared.auth import AuthIdentity
from shared.context import bound_context

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
        "eval_run_concurrency": 4,
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
    """Answer `search_chunks` from a table, tracking overlap and failures."""

    def __init__(
        self,
        responses: Optional[Dict[str, Any]] = None,
        *,
        fail_queries: Optional[set] = None,
    ) -> None:
        self.responses = responses if responses is not None else RESPONSES
        self.fail_queries = fail_queries or set()
        self.calls: List[Dict[str, Any]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def search_chunks(self, request, query, retrieval_plan=None, pass_name="pass_one"):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self.calls.append({"query": query, "pass_name": pass_name, "tenant": request.tenant_id})
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

def test_a_run_returns_immediately_in_running_state():
    """The RPC must not block: a synchronous run would blow the timeout."""
    store, runner, _, dataset_id = build()

    async def _go():
        run = await runner.start_run(dataset_id)
        assert run["status"] == "running"
        await asyncio.gather(*list(runner._tasks))
        return run

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_aggregate_scores_match_the_known_orderings():
    """Relevant chunk at rank 1 and rank 3: MRR = (1 + 1/3) / 2."""
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    results = fetch(store, run["run_id"])["results"]

    assert results["items_evaluated"] == 2
    assert results["items_skipped"] == 0
    assert results["items_failed"] == 0
    assert results["mrr"] == pytest.approx((1 + 1 / 3) / 2)
    assert results["recall_at_k"]["1"] == pytest.approx(0.5)
    assert results["recall_at_k"]["3"] == pytest.approx(1.0)
    assert results["hit_rate_at_k"]["1"] == pytest.approx(0.5)
    assert results["hit_rate_at_k"]["3"] == pytest.approx(1.0)


def test_the_run_records_where_the_first_hit_landed_per_item():
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    rows = {row["query"]: row for row in fetch(store, run["run_id"])["per_item"]}

    assert rows["first"]["first_hit_rank"] == 1
    assert rows["third"]["first_hit_rank"] == 3
    assert rows["third"]["reciprocal_rank"] == pytest.approx(1 / 3)


def test_partial_progress_is_persisted_as_items_complete():
    """A crashed run must leave evidence of how far it got."""
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)

    assert len(fetch(store, run["run_id"])["per_item"]) == 2


def test_retrieval_is_tagged_as_an_eval_sweep_and_carries_the_tenant():
    store, runner, backend, dataset_id = build()
    execute(runner, dataset_id)

    assert {call["pass_name"] for call in backend.calls} == {"eval"}
    assert {call["tenant"] for call in backend.calls} == {"tenant-a"}


def test_the_run_captures_a_config_snapshot_naming_what_it_cannot_see():
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    snapshot = fetch(store, run["run_id"])["config_snapshot"]

    assert snapshot["top_k_documents"] == 6
    assert snapshot["reranker_enabled"] is True
    # Not stored as a silent null: a diff must not read two unknown embedding
    # models as a match.
    assert "embedding_model" in snapshot["unobserved"]


# ── Failure paths ─────────────────────────────────────────────────────────

def test_a_run_whose_every_item_fails_is_marked_failed():
    backend = FakeBackend(fail_queries={"first", "third"})
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    fetched = fetch(store, run["run_id"])

    assert fetched["status"] == "failed"
    assert "embedding unavailable" in fetched["error"]
    assert fetched["finished_at"] is not None


def test_one_failing_item_does_not_discard_the_others():
    backend = FakeBackend(fail_queries={"third"})
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    fetched = fetch(store, run["run_id"])

    assert fetched["status"] == "completed"
    assert fetched["results"]["items_failed"] == 1
    assert fetched["results"]["items_evaluated"] == 1
    # The surviving item scored perfectly; the failed one is excluded, not
    # averaged in as a zero.
    assert fetched["results"]["mrr"] == pytest.approx(1.0)


def test_a_crash_inside_the_runner_still_closes_the_run():
    """`running` is indistinguishable from in-progress, so it must never
    be the resting state of a broken run."""
    store, runner, _, dataset_id = build()

    def explode(*args, **kwargs):
        raise RuntimeError("mongo write failed")

    runner.store.append_item_result = explode  # type: ignore[assignment]
    run = execute(runner, dataset_id)
    fetched = fetch(store, run["run_id"])

    assert fetched["status"] == "failed"
    assert "mongo write failed" in fetched["error"]


def test_starting_a_run_for_an_unknown_dataset_writes_no_run_document():
    store, runner, _, _ = build()

    async def _go():
        with pytest.raises(Exception):
            await runner.start_run("does-not-exist")

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())
        assert store.list_runs() == []


def test_an_empty_dataset_is_refused_before_a_run_is_opened():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    runner = EvalRunner(config, store, FakeBackend())  # type: ignore[arg-type]
    with bound_context(**ADMIN.to_dict()):
        dataset = store.create_dataset("A", None, ITEMS)
        # Bypass validation the way a corrupted document would.
        store._docs("eval_datasets")[0]["items"] = []

        async def _go():
            with pytest.raises(EvalValidationError):
                await runner.start_run(dataset["dataset_id"])

        asyncio.run(_go())
        assert store.list_runs() == []


# ── Concurrency ───────────────────────────────────────────────────────────

def test_concurrency_stays_within_the_semaphore_bound():
    """An unbounded gather over a large dataset would bury the embedding
    service, which is serving live traffic from the same instance."""
    items = [
        {"query": f"q{index}", "relevant_chunk_ids": ["c1"]} for index in range(12)
    ]
    backend = FakeBackend(responses={})
    store, runner, backend, dataset_id = build(
        items=items, backend=backend, eval_run_concurrency=3
    )
    execute(runner, dataset_id)

    assert backend.max_in_flight <= 3
    assert len(backend.calls) == 12


# ── Match modes ───────────────────────────────────────────────────────────

def test_a_fully_chunk_labelled_dataset_matches_on_chunk_id():
    assert dataset_match_mode([{"relevant_chunk_ids": ["c"]}]) == MATCH_CHUNK


def test_a_file_only_dataset_falls_back_to_file_id():
    assert dataset_match_mode([{"relevant_file_ids": ["f"]}]) == MATCH_FILE


def test_an_inconsistently_labelled_dataset_is_marked_mixed():
    """Scoring half the items against the wrong id field would be silent
    nonsense, so the run says `mixed` and each row records its own mode."""
    items = [{"relevant_chunk_ids": ["c"]}, {"relevant_file_ids": ["f"]}]
    assert dataset_match_mode(items) == MATCH_MIXED


def test_mixed_mode_prefers_chunk_ids_per_item():
    item = {"relevant_chunk_ids": ["c"], "relevant_file_ids": ["f"]}
    assert relevant_ids(item, MATCH_MIXED) == {"c"}


def test_file_mode_scores_against_file_ids():
    backend = FakeBackend(
        responses={"by file": {"chunks": [{"chunk_id": "c1", "file_id": "f9"}]}}
    )
    store, runner, _, dataset_id = build(
        items=[{"query": "by file", "relevant_file_ids": ["f9"]}], backend=backend
    )
    run = execute(runner, dataset_id)
    fetched = fetch(store, run["run_id"])

    assert fetched["match_mode"] == MATCH_FILE
    assert fetched["results"]["hit_rate_at_k"]["1"] == pytest.approx(1.0)


# ── Response parsing ──────────────────────────────────────────────────────

def test_chunks_the_app_would_refuse_to_use_are_not_scored():
    """Scoring filtered-out chunks would measure a retriever that does not
    exist — the policy gate is part of the retrieval being evaluated."""
    response = {
        "chunks": [
            {"chunk_id": "keep"},
            {"chunk_id": "removed", "review_status": "removed"},
            {"chunk_id": "blocked", "retrieval_allowed": False},
        ]
    }
    assert retrieved_ids(eligible_chunks(response), MATCH_CHUNK) == ["keep"]


def test_the_qdrant_nested_payload_shape_is_understood():
    response = {"chunks": [{"payload": {"chunk_id": "nested", "review_status": "clean"}}]}
    assert retrieved_ids(eligible_chunks(response), MATCH_CHUNK) == ["nested"]


def test_file_mode_falls_back_to_document_id():
    response = {"chunks": [{"chunk_id": "c1", "document_id": "d1"}]}
    assert retrieved_ids(eligible_chunks(response), MATCH_FILE) == ["d1"]


# ── Aggregation ───────────────────────────────────────────────────────────

def test_unlabelled_items_are_excluded_from_the_means_and_counted():
    """A half-labelled dataset must show as a small denominator, never as a
    retrieval regression."""
    rows = [
        {
            "reciprocal_rank": 1.0,
            "latency_ms": 10.0,
            "scores": {
                "recall_at_k": {str(k): 1.0 for k in (1, 3, 5, 10, 20)},
                "precision_at_k": {str(k): 1.0 for k in (1, 3, 5, 10, 20)},
                "hit_rate_at_k": {str(k): 1.0 for k in (1, 3, 5, 10, 20)},
                "ndcg_at_k": {str(k): 1.0 for k in (1, 3, 5, 10, 20)},
            },
        },
        {"skipped": True, "latency_ms": 5.0},
    ]
    results = aggregate(rows)

    assert results["items_evaluated"] == 1
    assert results["items_skipped"] == 1
    assert results["recall_at_k"]["5"] == pytest.approx(1.0)
    assert results["mean_latency_ms"] == pytest.approx(7.5)


def test_a_run_with_nothing_scorable_reports_none_not_zero():
    """A mean over nothing is unknown. "Recall@5: 0%" would be a lie."""
    results = aggregate([{"skipped": True}])

    assert results["mrr"] is None
    assert results["recall_at_k"]["5"] is None
    assert results["items_evaluated"] == 0
