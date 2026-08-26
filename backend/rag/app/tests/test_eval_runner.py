"""Tests for the eval runner: aggregate correctness, failure paths, bounds.

The backend client is a double returning known orderings, so every expected
aggregate below is hand-computable. Nothing here touches RabbitMQ, MongoDB or
an LLM — which is also the runner's own contract: it must never call one.

Async tests are written as sync functions driving ``asyncio.run``, matching
``test_rag.py``. That keeps the suite independent of pytest-asyncio.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from app.services.eval_runner import (
    K_VALUES,
    MATCH_CHUNK,
    MATCH_FILE,
    MATCH_MIXED,
    MODE_END_TO_END,
    MODE_RETRIEVAL,
    PIPELINE_EXTENDED,
    PIPELINE_REGULAR,
    STALE_POLICY_FAIL,
    STALE_POLICY_UNSCORABLE,
    EvalRunner,
    aggregate,
    candidate_depth,
    classify_labels,
    dataset_match_mode,
    eligible_chunks,
    label_targets,
    relevant_ids,
    retrieved_ids,
    stale_label_policy,
)
from app.services.eval_store import EvalStore, EvalValidationError
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


def test_eval_searches_run_in_the_eval_traffic_class():
    _, runner, backend, dataset_id = build()
    execute(runner, dataset_id)

    assert [call["traffic_class"] for call in backend.calls] == ["eval", "eval"]


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


# ── Candidate depth ───────────────────────────────────────────────────────

def test_eval_retrieval_asks_for_every_rank_it_reports():
    """Recall@20 over six candidates would be Recall@6 under another name."""
    store, runner, backend, dataset_id = build()
    execute(runner, dataset_id)

    assert 20 in K_VALUES
    assert {call["top_k"] for call in backend.calls} == {20}


def test_candidate_depth_is_floored_at_the_largest_reported_k():
    """A depth below max(K_VALUES) is a k the run could never observe."""
    assert candidate_depth(build_config(eval_candidate_k=5)) == max(K_VALUES)
    assert candidate_depth(build_config(eval_candidate_k=50)) == 50

    store, runner, backend, dataset_id = build(eval_candidate_k=5)
    execute(runner, dataset_id)

    assert {call["top_k"] for call in backend.calls} == {max(K_VALUES)}


def test_recall_at_twenty_can_see_a_hit_below_the_production_top_k():
    """The bug this guards: a rank-12 hit scored 0.0 at every k above 6."""
    deep = ["c%d" % index for index in range(1, 21)]
    backend = FakeBackend({"deep": {"chunks": [{"chunk_id": cid} for cid in deep]}})
    store, runner, _, dataset_id = build(
        items=[{"query": "deep", "relevant_chunk_ids": ["c12"]}],
        backend=backend,
    )
    run = execute(runner, dataset_id)
    results = fetch(store, run["run_id"])["results"]

    assert results["recall_at_k"]["20"] == 1.0
    assert results["recall_at_k"]["10"] == 0.0
    assert results["mrr"] == pytest.approx(1 / 12)


def test_the_run_captures_a_config_snapshot_naming_what_it_cannot_see():
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    snapshot = fetch(store, run["run_id"])["config_snapshot"]

    assert snapshot["top_k_documents"] == 6
    # Recorded separately from the production depth: the run's ranking was
    # drawn from twenty candidates, not from the six an answer is built from.
    assert snapshot["candidate_k"] == 20
    assert snapshot["retrieval_strategy"] == "dense_vector"
    # Not stored as a silent null: a diff must not read two unknown embedding
    # models as a match.
    assert "embedding_model" in snapshot["unobserved"]
    assert "chunk_size" in snapshot["unobserved"]


def test_a_retrieval_run_cannot_claim_a_reranker_a_legacy_flag_turned_on():
    """The acceptance criterion at the run level. `reranker_enabled` and
    `hybrid_search_enabled` default to true and nothing in the request path
    reads either, so a run must not report them as what produced its
    numbers."""
    store, runner, _, dataset_id = build()
    assert runner.config.reranker_enabled is True
    assert runner.config.hybrid_search_enabled is True

    run = execute(runner, dataset_id)
    snapshot = fetch(store, run["run_id"])["config_snapshot"]

    assert snapshot["reranker_active"] is False
    assert snapshot["reranker_model"] is None
    assert snapshot["hybrid_search_active"] is False
    for legacy in (
        "reranker_enabled",
        "reranker_top_k",
        "hybrid_search_enabled",
        "hybrid_search_alpha",
        "min_similarity_threshold",
    ):
        assert legacy not in snapshot


def test_a_retrieval_run_records_no_stage_it_never_reached():
    """It issues one `search_chunks` call: no merge, no pass two, no answer
    context. The production values for those would name work it never did."""
    store, runner, _, dataset_id = build()

    run = execute(runner, dataset_id)
    snapshot = fetch(store, run["run_id"])["config_snapshot"]

    assert snapshot["context_k"] is None
    assert snapshot["merge_kept_k"] is None
    assert snapshot["pass_two_active"] is False
    assert snapshot["pass_two_score_threshold"] is None
    # None of those nulls is a gap in what rag could see, so none of them may
    # appear alongside the env-sourced fields that genuinely are.
    for field in ("context_k", "merge_kept_k", "reranker_model"):
        assert field not in snapshot["unobserved"]


def test_a_stored_snapshot_written_before_versioning_reads_back_as_version_one():
    """Older run documents stay readable. The legacy keys are left exactly as
    that run recorded them — they are its provenance — and the stamp is what
    tells a reader to interpret them as config's declaration rather than as a
    claim about what ran."""
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    legacy_snapshot = {"top_k_documents": 6, "reranker_enabled": True}
    with bound_context(**ADMIN.to_dict()):
        stored = store._find_one(
            store.config.eval_runs_collection,
            {"tenant_id": ADMIN.tenant_id, "run_id": run["run_id"]},
        )
        stored["config_snapshot"] = legacy_snapshot

        snapshot = store.get_run(run["run_id"])["config_snapshot"]

    assert snapshot["snapshot_version"] == 1
    assert snapshot["reranker_enabled"] is True
    assert snapshot["top_k_documents"] == 6


def test_the_run_snapshots_the_dataset_version_and_fingerprint():
    """`dataset_id` alone cannot prove which labels a run scored: the items
    behind it can be replaced. The run copies the pair at start."""
    store, runner, _, dataset_id = build()
    with bound_context(**ADMIN.to_dict()):
        dataset = store.get_dataset(dataset_id)

    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])

    assert stored["dataset_version"] == dataset["dataset_version"] == 1
    assert stored["dataset_sha256"] == dataset["dataset_sha256"]


def test_relabelling_a_dataset_does_not_rewrite_what_past_runs_scored():
    """The regression evidence has to stay evidence. An edit after a run
    moves the dataset forward and leaves the finished run describing the
    labels it actually used."""
    store, runner, _, dataset_id = build()
    first = fetch(store, execute(runner, dataset_id)["run_id"])

    with bound_context(**ADMIN.to_dict()):
        store.update_dataset(
            dataset_id,
            items=[{"query": "first", "relevant_chunk_ids": ["relabelled"]}],
        )
    second = fetch(store, execute(runner, dataset_id)["run_id"])
    unchanged = fetch(store, first["run_id"])

    assert unchanged["dataset_version"] == first["dataset_version"] == 1
    assert unchanged["dataset_sha256"] == first["dataset_sha256"]
    assert second["dataset_version"] == 2
    assert second["dataset_sha256"] != first["dataset_sha256"]


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


def test_unresolved_authoring_filenames_are_refused_before_a_run_is_opened():
    store, runner, _, dataset_id = build(
        items=[{"item_id": "q1", "query": "Where?", "expected_file_names": ["guide.md"]}]
    )

    async def _go():
        with pytest.raises(EvalValidationError, match="unresolved expected_file_names"):
            await runner.start_run(dataset_id)

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())
        assert store.list_runs() == []


def test_import_preparation_resolves_filenames_before_storage():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = FakeBackend(
        resolutions=[
            {"label": "Guide.pdf", "status": "RESOLVED", "file_id": "file-1"}
        ]
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps([{"query": "Where?", "expected_file_names": ["Guide.pdf"]}])

    async def _go():
        validation = await runner.handle(
            "validate_eval_dataset", {"content": content, "format": "json"}
        )
        imported = await runner.handle(
            "create_eval_dataset",
            {"name": "Prepared", "content": content, "format": "json"},
        )
        return validation, imported

    with bound_context(**ADMIN.to_dict()):
        validation, imported = asyncio.run(_go())
        dataset = store.get_dataset(imported["dataset"]["dataset_id"])

    assert validation["preparation"] == {
        "ready": 1,
        "unresolved": 0,
        "ambiguous": 0,
        "unanswerable": 0,
        "chunk_ready": 0,
        "file_fallback": 0,
        "resolved_facts": 0,
        "unresolved_facts": 0,
        "unready_files": 0,
        "unready_items": 0,
        "blocking": False,
        "warnings": [],
    }
    assert dataset["items"][0]["relevant_file_ids"] == ["file-1"]


def test_import_preparation_blocks_missing_and_ambiguous_filenames_with_codes():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = FakeBackend(
        resolutions=[
            {"label": "missing.pdf", "status": "UNRESOLVED_FILE", "file_id": None},
            {"label": "copy.pdf", "status": "AMBIGUOUS_FILE_MATCH", "file_id": None},
        ]
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps(
        [
            {"query": "Missing?", "expected_file_names": ["missing.pdf"]},
            {"query": "Which copy?", "expected_file_names": ["copy.pdf"]},
        ]
    )

    async def _go():
        return await runner.handle(
            "validate_eval_dataset", {"content": content, "format": "json"}
        )

    with bound_context(**ADMIN.to_dict()):
        result = asyncio.run(_go())

    assert result["validation"]["valid"] is False
    assert result["preparation"]["unresolved"] == 1
    assert result["preparation"]["ambiguous"] == 1
    assert [error["code"] for error in result["validation"]["errors"]] == [
        "UNRESOLVED_FILE",
        "AMBIGUOUS_FILE_MATCH",
    ]


def test_import_preparation_resolves_exact_facts_to_all_matching_chunks():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = FakeBackend(
        resolutions=[{"label": "Guide.pdf", "status": "RESOLVED", "file_id": "file-1"}],
        chunk_resolutions=[
            {
                "item_id": "q1",
                "files": [{"file_id": "file-1", "status": "READY", "searchable": True}],
                "facts": [
                    {
                        "fact": "Refunds are available for 30 days.",
                        "status": "RESOLVED",
                        "chunk_ids": ["c1", "c2"],
                    }
                ],
                "chunk_ids": ["c1", "c2"],
            }
        ],
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps(
        [
            {
                "item_id": "q1",
                "query": "Refund window?",
                "expected_file_names": ["Guide.pdf"],
                "expected_facts": ["Refunds are available for 30 days."],
            }
        ]
    )

    async def _go():
        return await runner.handle(
            "create_eval_dataset",
            {"name": "Prepared", "content": content, "format": "json"},
        )

    with bound_context(**ADMIN.to_dict()):
        imported = asyncio.run(_go())
        dataset = store.get_dataset(imported["dataset"]["dataset_id"])

    item = dataset["items"][0]
    assert item["relevant_file_ids"] == ["file-1"]
    assert item["relevant_chunk_ids"] == ["c1", "c2"]
    assert item["unresolved_expected_facts"] == []
    assert imported["preparation"]["chunk_ready"] == 1
    assert imported["preparation"]["resolved_facts"] == 1


def test_unresolved_fact_is_explicit_and_keeps_file_level_eval_usable():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    fact = "Refunds are available for 30 days."
    backend = FakeBackend(
        resolutions=[{"label": "Guide.pdf", "status": "RESOLVED", "file_id": "file-1"}],
        chunk_resolutions=[
            {
                "item_id": "q1",
                "files": [{"file_id": "file-1", "status": "READY", "searchable": True}],
                "facts": [{"fact": fact, "status": "UNRESOLVED_FACT", "chunk_ids": []}],
                "chunk_ids": [],
            }
        ],
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps(
        [
            {
                "item_id": "q1",
                "query": "Refund window?",
                "expected_file_names": ["Guide.pdf"],
                "expected_facts": [fact],
            }
        ]
    )

    async def _go():
        return await runner.handle(
            "create_eval_dataset",
            {"name": "Fallback", "content": content, "format": "json"},
        )

    with bound_context(**ADMIN.to_dict()):
        imported = asyncio.run(_go())
        dataset = store.get_dataset(imported["dataset"]["dataset_id"])

    item = dataset["items"][0]
    assert item["relevant_chunk_ids"] == []
    assert item["relevant_file_ids"] == ["file-1"]
    assert item["unresolved_expected_facts"] == [fact]
    assert imported["preparation"]["blocking"] is False
    assert imported["preparation"]["file_fallback"] == 1
    assert imported["preparation"]["warnings"][0]["code"] == "UNRESOLVED_FACT"


def test_unsearchable_file_blocks_import_readiness():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = FakeBackend(
        resolutions=[{"label": "Guide.pdf", "status": "RESOLVED", "file_id": "file-1"}],
        chunk_resolutions=[
            {
                "item_id": "q1",
                "files": [
                    {
                        "file_id": "file-1",
                        "status": "FILE_NOT_SEARCHABLE",
                        "searchable": False,
                    }
                ],
                "facts": [],
                "chunk_ids": [],
            }
        ],
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps(
        [{"item_id": "q1", "query": "Where?", "expected_file_names": ["Guide.pdf"]}]
    )

    async def _go():
        return await runner.handle(
            "validate_eval_dataset", {"content": content, "format": "json"}
        )

    with bound_context(**ADMIN.to_dict()):
        result = asyncio.run(_go())

    assert result["validation"]["valid"] is False
    assert result["preparation"]["blocking"] is True
    assert result["preparation"]["unready_files"] == 1
    assert result["validation"]["errors"][0]["code"] == "FILE_NOT_SEARCHABLE"


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


# ── end_to_end mode ───────────────────────────────────────────────────────

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
        return self.results.get(request.user_message, {})


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


def test_retrieval_stays_the_default_mode():
    """The free run is what a caller gets by saying nothing."""
    store, runner, backend, dataset_id = build()

    run = execute(runner, dataset_id)

    assert fetch(store, run["run_id"])["mode"] == MODE_RETRIEVAL
    assert fetch(store, run["run_id"])["config_snapshot"]["mode"] == MODE_RETRIEVAL


def test_default_run_never_touches_the_graph():
    """The phase-5 promise: a retrieval run costs nothing."""
    store, runner, backend, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    execute(runner, dataset_id)

    assert runner.graph_runner.calls == []


def test_end_to_end_mode_is_refused_without_a_graph():
    """Better a refusal than a run whose answer columns are silently blank."""
    store, runner, _, dataset_id = build()

    async def _go():
        with pytest.raises(EvalValidationError):
            await runner.start_run(dataset_id, MODE_END_TO_END)

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_an_unknown_mode_is_refused():
    store, runner, _, dataset_id = build()

    async def _go():
        with pytest.raises(EvalValidationError):
            await runner.start_run(dataset_id, "cheap")

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_a_retrieval_run_records_no_pipeline_it_did_not_drive():
    """Its one search is not routed through a conversation pipeline."""
    store, runner, _, dataset_id = build()

    run = fetch(store, execute(runner, dataset_id)["run_id"])

    assert run["pipeline_mode"] is None
    assert run["config_snapshot"]["pipeline_mode"] is None


def test_a_pipeline_mode_on_a_retrieval_run_is_refused_not_ignored():
    """Accepting it would let identical runs record different pipelines."""
    store, runner, _, dataset_id = build()

    async def _go():
        with pytest.raises(EvalValidationError):
            await runner.start_run(dataset_id, MODE_RETRIEVAL, PIPELINE_EXTENDED)

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_an_unknown_pipeline_mode_is_refused():
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    async def _go():
        with pytest.raises(EvalValidationError):
            await runner.start_run(dataset_id, MODE_END_TO_END, "turbo")

    with bound_context(**ADMIN.to_dict()):
        asyncio.run(_go())


def test_an_end_to_end_run_defaults_to_the_regular_pipeline():
    """Saying nothing must not leave the axis unrecorded."""
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    run = fetch(store, run_end_to_end(runner, dataset_id)["run_id"])

    assert run["pipeline_mode"] == PIPELINE_REGULAR


def test_an_extended_run_drives_the_extended_pipeline():
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    async def _go():
        run = await runner.start_run(dataset_id, MODE_END_TO_END, PIPELINE_EXTENDED)
        await asyncio.gather(*list(runner._tasks))
        return run

    with bound_context(**ADMIN.to_dict()):
        run = asyncio.run(_go())

    assert fetch(store, run["run_id"])["pipeline_mode"] == PIPELINE_EXTENDED
    assert {call["pipeline_mode"] for call in runner.graph_runner.calls} == {
        PIPELINE_EXTENDED
    }


def test_end_to_end_run_reports_answer_quality_and_retrieval():
    """Both halves are scored: the run replaces neither measure."""
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    run = run_end_to_end(runner, dataset_id)
    results = fetch(store, run["run_id"])["results"]
    quality = results["answer_quality"]

    assert results["mrr"] == pytest.approx((1.0 + 1.0) / 2)
    assert quality["groundedness"]["mean"] == pytest.approx(0.7)
    # One of the two items cited nothing, so precision is a mean of one.
    assert quality["citation_precision"] == {"mean": 1.0, "counted": 1, "excluded": 1}
    assert quality["citation_recall"]["mean"] == pytest.approx(0.5)
    assert quality["hallucination_rate"] == pytest.approx(0.5)
    assert quality["hallucination_severe_rate"] == pytest.approx(0.5)
    assert quality["items_judged"] == 2


def test_guardrail_blocked_items_are_separate_from_failures_and_answer_denominators():
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner({
        **GRAPH_RESULTS,
        "first": {"outcome": "guardrail_blocked", "guardrail_stage": "input", "sources": []},
    })

    run = run_end_to_end(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    blocked = next(row for row in stored["per_item"] if row["query"] == "first")

    assert blocked["outcome"] == "guardrail_blocked"
    assert blocked["guardrail_stage"] == "input"
    assert blocked["error"] is None
    assert stored["results"]["items_guardrail_blocked"] == 1
    assert stored["results"]["items_failed"] == 0
    assert stored["results"]["answer_quality"]["items_unjudged"] == 0


def test_end_to_end_turns_are_kept_out_of_the_live_turn_facts():
    """Synthetic turns must not move the averages the run is measuring."""
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    run_end_to_end(runner, dataset_id)

    assert runner.graph_runner.calls
    assert all(call["record_metrics"] is False for call in runner.graph_runner.calls)


def test_end_to_end_mode_is_recorded_in_the_config_snapshot():
    """So the config-diff warning fires when the two modes are compared."""
    store, runner, _, dataset_id = build()
    runner.graph_runner = FakeGraphRunner(GRAPH_RESULTS)

    run = run_end_to_end(runner, dataset_id)
    stored = fetch(store, run["run_id"])

    assert stored["mode"] == MODE_END_TO_END
    assert stored["config_snapshot"]["mode"] == MODE_END_TO_END
    # Scored over the graph's own sources, so the depth recorded is the
    # production one — claiming the eval depth would name a candidate pool
    # this run never saw.
    assert stored["config_snapshot"]["candidate_k"] == 6
    # This mode does drive the graph, so the stages it reaches are recorded
    # with their real settings rather than as null.
    assert stored["config_snapshot"]["context_k"] == 6
    assert stored["config_snapshot"]["reranker_implementation"] == "score_order_merge"
    assert stored["config_snapshot"]["pass_two_active"] is True


def test_end_to_end_respects_the_phase_five_concurrency_bound():
    """The heavier mode gets the same bound, not a larger one."""
    store, runner, _, dataset_id = build(
        items=[{"query": f"q{i}", "relevant_chunk_ids": ["c1"]} for i in range(8)],
        eval_run_concurrency=2,
    )

    class CountingGraph(FakeGraphRunner):
        def __init__(self):
            super().__init__({})
            self.in_flight = 0
            self.max_in_flight = 0

        async def run(self, request, emitter, resume=False, record_metrics=True):
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            try:
                await asyncio.sleep(0)
                return {"answer": "", "sources": [], "review": {}}
            finally:
                self.in_flight -= 1

    runner.graph_runner = CountingGraph()
    run_end_to_end(runner, dataset_id)

    assert runner.graph_runner.max_in_flight <= 2


def test_an_unjudged_item_is_excluded_from_the_hallucination_rate():
    """A flaky judge must not read as an answer that did not hallucinate."""
    rows = [
        {"hallucination_verdict": "severe", "groundedness": 0.2},
        {"hallucination_verdict": None, "groundedness": None},
    ]

    quality = aggregate(rows, MODE_END_TO_END)["answer_quality"]

    assert quality["hallucination_rate"] == 1.0
    assert quality["items_judged"] == 1
    assert quality["items_unjudged"] == 1


def test_retrieval_results_carry_no_answer_quality_section():
    """A free run reports nothing it did not measure."""
    assert "answer_quality" not in aggregate([{"skipped": True}], MODE_RETRIEVAL)


# -- Stale golden-set labels ----------------------------------------------
#
# A dataset labelled against an older index can name chunks reindexing has
# since dropped. Retrieval cannot return an id that no longer exists, so
# scoring the label as a miss reports a recall regression that never
# happened. These cover the three states a label can be in and what a run
# does about each.


def validation(store: EvalStore, run_id: str) -> Dict[str, Any]:
    return fetch(store, run_id)["label_validation"]


def test_a_deleted_chunk_label_fails_the_run_before_anything_is_scored():
    """Fail-fast is the default: a rotted golden set measures nothing."""
    backend = FakeBackend(index={"c1"})
    store, runner, backend, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])

    assert stored["status"] == "failed"
    assert "no longer exist" in stored["error"]
    # Nothing was retrieved, so nothing was scored against a dead label.
    assert backend.calls == []
    assert stored["per_item"] == []


def test_the_refused_run_stores_the_counts_and_the_affected_item():
    backend = FakeBackend(index={"c1"})
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    report = validation(store, run["run_id"])

    assert report["checked"] is True
    assert report["stale_label_count"] == 1
    assert report["stale_item_count"] == 1
    assert report["stale_ids"] == ["c9"]
    assert len(report["stale_item_ids"]) == 1
    assert report["policy"] == STALE_POLICY_FAIL


def test_stale_labels_are_never_scored_as_retrieval_misses():
    """The bug this feature exists to prevent, under the lenient policy."""
    backend = FakeBackend(index={"c1"})
    store, runner, _, dataset_id = build(
        backend=backend, eval_stale_label_policy=STALE_POLICY_UNSCORABLE
    )
    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    results = stored["results"]

    assert stored["status"] == "completed"
    # One item was scorable and its label ranked first. Counting the stale
    # item as a miss would have reported Recall@10 of 0.5.
    assert results["items_evaluated"] == 1
    assert results["items_unscorable"] == 1
    assert results["recall_at_k"]["10"] == pytest.approx(1.0)
    assert results["mrr"] == pytest.approx(1.0)


def test_an_unscorable_item_is_marked_and_never_retrieved():
    backend = FakeBackend(index={"c1"})
    store, runner, backend, dataset_id = build(
        backend=backend, eval_stale_label_policy=STALE_POLICY_UNSCORABLE
    )
    run = execute(runner, dataset_id)
    rows = {row["query"]: row for row in fetch(store, run["run_id"])["per_item"]}

    assert rows["third"]["unscorable"] is True
    assert rows["third"]["skipped"] is False
    assert rows["third"].get("scores") is None
    assert rows["first"]["unscorable"] is False
    # Only the scorable item cost an embed call.
    assert [call["query"] for call in backend.calls] == ["first"]


def test_a_label_present_but_barred_from_retrieval_is_reported_separately():
    """"Deleted" and "suppressed" call for different fixes."""
    backend = FakeBackend(index={"c1", "c9"}, barred={"c9"})
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    report = validation(store, run["run_id"])

    assert report["stale_label_count"] == 0
    assert report["unretrievable_label_count"] == 1
    assert report["unretrievable_ids"] == ["c9"]
    assert report["unscorable_item_count"] == 1
    assert fetch(store, run["run_id"])["status"] == "failed"


def test_a_fully_valid_golden_set_runs_and_records_a_clean_check():
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])

    assert stored["status"] == "completed"
    assert stored["label_validation"]["checked"] is True
    assert stored["label_validation"]["stale_label_count"] == 0
    assert stored["label_validation"]["labels_checked"] == 2
    assert stored["results"]["items_unscorable"] == 0


def test_file_level_labels_are_verified_too():
    backend = FakeBackend(
        {"only": {"chunks": [{"file_id": "f1"}]}}, index={"f1"}
    )
    store, runner, _, dataset_id = build(
        items=[
            {"query": "only", "relevant_file_ids": ["f1"]},
            {"query": "gone", "relevant_file_ids": ["f-dropped"]},
        ],
        backend=backend,
    )
    run = execute(runner, dataset_id)
    report = validation(store, run["run_id"])

    assert backend.verify_calls[0]["file_ids"] == ["f-dropped", "f1"]
    assert report["stale_ids"] == ["f-dropped"]
    assert fetch(store, run["run_id"])["status"] == "failed"


def test_verification_asks_only_about_the_ids_the_run_will_score():
    """A mixed item scored on its chunk ids must not be checked on its file ids."""
    backend = FakeBackend({"both": {"chunks": [{"chunk_id": "c1"}]}})
    store, runner, backend, dataset_id = build(
        items=[
            # Labelled at both granularities: mixed mode scores it on the
            # finer one, so `f1` is never a label this run can miss.
            {"query": "both", "relevant_chunk_ids": ["c1"], "relevant_file_ids": ["f1"]},
            {"query": "chunk only", "relevant_chunk_ids": ["c2"]},
            {"query": "file only", "relevant_file_ids": ["f2"]},
        ],
        backend=backend,
    )
    execute(runner, dataset_id)

    assert backend.verify_calls[0]["chunk_ids"] == ["c1", "c2"]
    assert backend.verify_calls[0]["file_ids"] == ["f2"]


def test_labels_that_could_not_be_verified_leave_a_warning_not_a_silent_pass():
    """An unreachable vector_db must not read as "no stale labels"."""
    backend = FakeBackend(verify_error="vector_db unavailable")
    store, runner, _, dataset_id = build(backend=backend)
    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])
    report = stored["label_validation"]

    assert stored["status"] == "completed"
    assert report["checked"] is False
    assert report["reason"] == "unavailable"
    assert "vector_db unavailable" in report["error"]
    # None, not 0: nothing was measured, so no count may be claimed.
    assert report["stale_label_count"] is None


def test_validation_can_be_switched_off_and_says_so():
    store, runner, backend, dataset_id = build(eval_validate_labels=False)
    run = execute(runner, dataset_id)
    report = validation(store, run["run_id"])

    assert backend.verify_calls == []
    assert report["checked"] is False
    assert report["reason"] == "disabled"


def test_an_unknown_policy_falls_back_to_failing_rather_than_to_scoring():
    """A typo must not become the permissive branch."""
    assert stale_label_policy(build_config(eval_stale_label_policy="nonsense")) == (
        STALE_POLICY_FAIL
    )

    backend = FakeBackend(index={"c1"})
    store, runner, _, dataset_id = build(
        backend=backend, eval_stale_label_policy="nonsense"
    )
    run = execute(runner, dataset_id)

    assert fetch(store, run["run_id"])["status"] == "failed"


def test_label_targets_splits_ids_by_the_mode_each_item_is_scored_under():
    items = [
        {"query": "a", "relevant_chunk_ids": ["c1"], "relevant_file_ids": ["f1"]},
        {"query": "b", "relevant_file_ids": ["f2"]},
    ]

    assert label_targets(items, MATCH_MIXED) == ({"c1"}, {"f2"})
    assert label_targets(items, MATCH_FILE) == (set(), {"f1", "f2"})
    assert label_targets(items, MATCH_CHUNK) == ({"c1"}, set())


def test_classify_caps_the_reported_ids_but_never_the_counts():
    """A wholly stale dataset must not write its entire label set into the run."""
    items = [
        {"item_id": f"i{index}", "query": "q", "relevant_chunk_ids": [f"c{index}"]}
        for index in range(10)
    ]
    verified = {
        "chunk_ids": {
            "present": [],
            "retrievable": [],
            "missing": [f"c{index}" for index in range(10)],
        },
        "file_ids": {"present": [], "retrievable": [], "missing": []},
    }

    report = classify_labels(items, MATCH_CHUNK, verified, max_reported_ids=3)

    assert report.summary["stale_label_count"] == 10
    assert report.summary["stale_item_count"] == 10
    assert len(report.summary["stale_ids"]) == 3
    assert report.summary["truncated"] is True
    # The full set still drives which items are excluded from scoring.
    assert len(report.unscorable) == 10
