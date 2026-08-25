"""Tests for eval dataset/run persistence: tenancy and upload validation.

Two backends are exercised deliberately. Most tests run against the
in-memory store, because tenancy is a *behavioural* property — tenant B must
not be able to read tenant A's dataset — and asserting behaviour beats
asserting a query shape. One test then pins the MongoDB pipeline itself, so
that the tenant boundary provably sits in the first ``$match`` and is not
something applied to rows afterwards.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from app.services.eval_store import (
    RUN_COMPLETED,
    RUN_RUNNING,
    EvalAccessDenied,
    EvalNotFound,
    EvalStore,
    EvalValidationError,
)
from shared.auth import AuthIdentity
from shared.context import bound_context

ADMIN_A = AuthIdentity(tenant_id="tenant-a", user_id="admin-a", role="admin", admin_id="admin-a")
ADMIN_B = AuthIdentity(tenant_id="tenant-b", user_id="admin-b", role="admin", admin_id="admin-b")
USER_A = AuthIdentity(tenant_id="tenant-a", user_id="user-a", role="user", admin_id="admin-a")

ITEMS = [
    {"query": "What is the refund window?", "relevant_chunk_ids": ["c1", "c2"]},
    {"query": "Who signs the contract?", "relevant_file_ids": ["f9"]},
]


def build_store(**overrides: Any) -> EvalStore:
    """Build the store on a fake config, independent of any .env file."""
    settings: Dict[str, Any] = {
        "conversation_store_type": "in_memory",
        "eval_datasets_collection": "eval_datasets",
        "eval_runs_collection": "eval_runs",
        "eval_max_dataset_items": 1000,
        "eval_max_query_length": 2000,
        "mongodb_url": "mongodb://localhost:27017/",
        "mongodb_database": "rag",
        "mongodb_max_retries": 1,
        "mongodb_retry_delay": 0,
        "top_k_documents": 6,
    }
    settings.update(overrides)
    config = SimpleNamespace(**settings)
    return EvalStore(config)  # type: ignore[arg-type]


# ── Tenancy ───────────────────────────────────────────────────────────────

def test_a_dataset_is_visible_only_inside_its_own_tenant():
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        created = store.create_dataset("Support golden set", None, ITEMS)

    with bound_context(**ADMIN_B.to_dict()):
        assert store.list_datasets() == []
        with pytest.raises(EvalNotFound):
            store.get_dataset(created["dataset_id"])


def test_cross_tenant_read_reports_not_found_rather_than_denied():
    """Not-found, not access-denied: the reply must not confirm the id exists."""
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        created = store.create_dataset("A", None, ITEMS)

    with bound_context(**ADMIN_B.to_dict()):
        with pytest.raises(EvalNotFound):
            store.update_dataset(created["dataset_id"], name="hijacked")
        with pytest.raises(EvalNotFound):
            store.delete_dataset(created["dataset_id"])


@pytest.mark.parametrize(
    "call",
    [
        lambda store: store.list_datasets(),
        lambda store: store.create_dataset("A", None, ITEMS),
        lambda store: store.get_dataset("any"),
        lambda store: store.delete_dataset("any"),
        lambda store: store.list_runs(),
        lambda store: store.get_run("any"),
    ],
)
def test_every_read_and_write_requires_an_admin(call):
    store = build_store()
    with bound_context(**USER_A.to_dict()):
        with pytest.raises(EvalAccessDenied):
            call(store)


def test_an_unidentified_caller_is_refused_as_firmly_as_a_non_admin():
    store = build_store()
    with pytest.raises(EvalAccessDenied):
        store.list_datasets()


def test_the_tenant_boundary_is_in_the_first_match_stage():
    """Pin the pipeline shape: scoping happens in MongoDB, not in Python."""
    store = build_store()
    recorder = FakeDatabase()
    store._in_memory = False
    store._db = recorder

    with bound_context(**ADMIN_A.to_dict()):
        store.list_datasets()

    first_stage = recorder.pipelines[0][1][0]
    assert first_stage == {"$match": {"tenant_id": "tenant-a"}}
    # Every pipeline the call issued, not just the first one.
    for _, pipeline in recorder.pipelines:
        assert pipeline[0]["$match"]["tenant_id"] == "tenant-a"


def test_background_writes_stay_scoped_without_a_bound_identity():
    """`finish_run` runs in a task with no request context, so it takes the
    tenant explicitly — and must still put it in the filter."""
    store = build_store()
    recorder = FakeDatabase()
    store._in_memory = False
    store._db = recorder

    store.finish_run("run-1", "tenant-a", status=RUN_COMPLETED, results={})

    collection, filters, _ = recorder.updates[0]
    assert collection == "eval_runs"
    assert filters == {"tenant_id": "tenant-a", "run_id": "run-1"}


# ── Validation ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "items, message",
    [
        ([], "at least one item"),
        ("not a list", "at least one item"),
        ([{"relevant_chunk_ids": ["c1"]}], "no query"),
        ([{"query": "   ", "relevant_chunk_ids": ["c1"]}], "no query"),
        ([{"query": "q"}], "no relevant_chunk_ids or relevant_file_ids"),
        ([{"query": "q", "relevant_chunk_ids": []}], "no relevant_chunk_ids"),
        ([{"query": "q", "relevant_chunk_ids": "c1"}], "must be a list"),
        (["not an object"], "not an object"),
    ],
)
def test_malformed_items_are_rejected_with_a_reason(items, message):
    """Reject rather than truncate: a half-accepted dataset produces
    confident, wrong recall numbers, which is worse than an upload error."""
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        with pytest.raises(EvalValidationError, match=message):
            store.create_dataset("A", None, items)


def test_oversized_datasets_are_rejected_not_truncated():
    store = build_store(eval_max_dataset_items=3)
    items = [{"query": f"q{i}", "relevant_chunk_ids": ["c"]} for i in range(4)]
    with bound_context(**ADMIN_A.to_dict()):
        with pytest.raises(EvalValidationError, match="the limit is 3"):
            store.create_dataset("A", None, items)


def test_overlong_queries_are_rejected():
    store = build_store(eval_max_query_length=10)
    items = [{"query": "x" * 11, "relevant_chunk_ids": ["c"]}]
    with bound_context(**ADMIN_A.to_dict()):
        with pytest.raises(EvalValidationError, match="the limit is 10"):
            store.create_dataset("A", None, items)


def test_repeated_item_ids_are_rejected():
    store = build_store()
    items = [
        {"item_id": "dup", "query": "a", "relevant_chunk_ids": ["c"]},
        {"item_id": "dup", "query": "b", "relevant_chunk_ids": ["c"]},
    ]
    with bound_context(**ADMIN_A.to_dict()):
        with pytest.raises(EvalValidationError, match="repeats item_id"):
            store.create_dataset("A", None, items)


def test_a_dataset_needs_a_name():
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        with pytest.raises(EvalValidationError, match="needs a name"):
            store.create_dataset("  ", None, ITEMS)


def test_accepted_items_are_normalized_with_generated_ids():
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        created = store.create_dataset("A", "  a set  ", ITEMS)

    assert created["description"] == "a set"
    items = created["items"]
    assert len({item["item_id"] for item in items}) == 2
    assert items[0]["relevant_file_ids"] == []
    assert items[1]["relevant_chunk_ids"] == []
    assert items[0]["notes"] is None


# ── Datasets ──────────────────────────────────────────────────────────────

def test_the_listing_carries_counts_not_item_bodies():
    """A 1000-item body per dataset would dwarf the rest of the payload."""
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        store.create_dataset("A", None, ITEMS)
        listed = store.list_datasets()

    assert listed[0]["item_count"] == 2
    assert "items" not in listed[0]
    assert listed[0]["last_run_at"] is None


def test_updating_items_replaces_them_wholesale():
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        created = store.create_dataset("A", None, ITEMS)
        updated = store.update_dataset(
            created["dataset_id"],
            name="Renamed",
            items=[{"query": "only one", "relevant_chunk_ids": ["c9"]}],
        )

    assert updated["name"] == "Renamed"
    assert len(updated["items"]) == 1
    assert updated["items"][0]["query"] == "only one"


def test_deleting_a_dataset_keeps_its_runs():
    """Runs are the regression evidence; deleting the labels must not erase
    what retrieval scored at the time."""
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        created = store.create_dataset("A", None, ITEMS)
        run = store.create_run(created["dataset_id"], {}, "chunk_id")
        store.delete_dataset(created["dataset_id"])

        assert store.list_datasets() == []
        assert [row["run_id"] for row in store.list_runs()] == [run["run_id"]]


# ── Runs ──────────────────────────────────────────────────────────────────

def test_a_new_run_opens_in_running_state_with_its_snapshot():
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        created = store.create_dataset("A", None, ITEMS)
        run = store.create_run(created["dataset_id"], {"top_k_documents": 6}, "chunk_id")

    assert run["status"] == RUN_RUNNING
    assert run["finished_at"] is None
    assert run["config_snapshot"] == {"top_k_documents": 6}
    assert run["match_mode"] == "chunk_id"


def test_item_results_accumulate_and_the_run_closes():
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        run = store.create_run("d-1", {}, "chunk_id")
        store.append_item_result(run["run_id"], "tenant-a", {"item_id": "i1"})
        store.append_item_result(run["run_id"], "tenant-a", {"item_id": "i2"})
        store.finish_run(run["run_id"], "tenant-a", status=RUN_COMPLETED, results={"mrr": 0.5})
        fetched = store.get_run(run["run_id"])

    assert [row["item_id"] for row in fetched["per_item"]] == ["i1", "i2"]
    assert fetched["status"] == RUN_COMPLETED
    assert fetched["results"] == {"mrr": 0.5}
    assert fetched["finished_at"] is not None


def test_the_run_listing_drops_per_item_rows():
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        run = store.create_run("d-1", {}, "chunk_id")
        store.append_item_result(run["run_id"], "tenant-a", {"item_id": "i1"})
        listed = store.list_runs("d-1")

    assert listed[0]["per_item"] == []


def test_runs_can_be_filtered_by_dataset():
    store = build_store()
    with bound_context(**ADMIN_A.to_dict()):
        store.create_run("d-1", {}, "chunk_id")
        second = store.create_run("d-2", {}, "chunk_id")
        listed = store.list_runs("d-2")

    assert [row["run_id"] for row in listed] == [second["run_id"]]


# ── MongoDB doubles ───────────────────────────────────────────────────────

class FakeCollection:
    """Record what the store asks MongoDB to do, and answer with nothing."""

    def __init__(self, database: "FakeDatabase", name: str) -> None:
        self._database = database
        self._name = name

    def aggregate(self, pipeline: List[Dict[str, Any]]):
        self._database.pipelines.append((self._name, pipeline))
        return iter(())

    def update_one(self, filters, update):
        self._database.updates.append((self._name, filters, update))
        return SimpleNamespace(matched_count=1)

    def delete_one(self, filters):
        self._database.deletes.append((self._name, filters))
        return SimpleNamespace(deleted_count=1)

    def insert_one(self, document):
        self._database.inserts.append((self._name, document))


class FakeDatabase:
    def __init__(self) -> None:
        self.pipelines: List[Any] = []
        self.updates: List[Any] = []
        self.deletes: List[Any] = []
        self.inserts: List[Any] = []

    def __getitem__(self, name: str) -> FakeCollection:
        return FakeCollection(self, name)
