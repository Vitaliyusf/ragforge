"""Closing the gap between canonical memory and the vector index.

MEMORY-V2-01 made every divergence between MongoDB and Qdrant explicit rather
than silent. These tests are about the other half of that promise: that a
recorded divergence actually gets repaired, that repairing it twice is free,
and that a repair which cannot complete says so instead of clearing the flag.
"""

from shared.context import bound_context

from app.tests._memory_harness import (
    BagOfWordsEmbeddingClient,
    FakeEmbeddingClient,
    FakeVectorIndex,
    InMemoryVectorIndex,
    build_memory_service,
    build_reconciliation_service,
    episodic_candidate,
)

IDENTITY = dict(tenant_id="tenant-a", user_id="user-1", role="user")
OTHER_TENANT = dict(tenant_id="tenant-b", user_id="user-9", role="user")


def _live_service():
    return build_memory_service(
        index_client=InMemoryVectorIndex(),
        embedding_client=BagOfWordsEmbeddingClient(),
    )


def _write(service, request_id, text="The user launched the beta milestone.", identity=None):
    with bound_context(**(identity or IDENTITY)):
        return service.write_memory(
            episodic_candidate(text),
            {"owner_type": "user", "request_id": request_id},
        )


def test_a_memory_whose_embedding_failed_is_indexed_on_the_next_pass():
    index = FakeVectorIndex(enabled=True)
    embedding = FakeEmbeddingClient(fail=True)
    service, database, _ = build_memory_service(index_client=index, embedding_client=embedding)
    written = _write(service, "req-r-1")
    assert written["reconciliation_required"] is True

    embedding.fail = False
    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    stored = database["episodic_memories"].docs[0]
    assert report["drift"]["missing_vector"] == 1
    assert report["repaired"] == 1
    assert report["failed"] == 0
    assert stored["retrieval"]["embedding_status"] == "indexed"
    assert stored["retrieval"]["indexed_revision"] == stored["revision"]


def test_a_repair_that_still_cannot_run_leaves_the_memory_marked_not_clean():
    index = FakeVectorIndex(enabled=True)
    embedding = FakeEmbeddingClient(fail=True)
    service, database, _ = build_memory_service(index_client=index, embedding_client=embedding)
    _write(service, "req-r-2")

    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    assert report["status"] == "partial"
    assert report["failed"] == 1
    assert report["repaired"] == 0
    assert report["unresolved"] == [database["episodic_memories"].docs[0]["id"]]
    # The flag survives, so the next pass tries again rather than believing a
    # repair that never happened.
    assert database["episodic_memories"].docs[0]["retrieval"]["embedding_status"] == "failed"


def test_a_vector_built_from_older_wording_is_rebuilt():
    service, database, _ = _live_service()
    written = _write(service, "req-r-3")
    collection = database["episodic_memories"]
    collection.update_one({"id": written["memory_id"]}, {"$set": {"revision": 7}})

    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    assert report["drift"]["stale_vector"] == 1
    assert report["repaired"] == 1
    assert collection.docs[0]["retrieval"]["indexed_revision"] == 7


def test_a_tombstoned_delete_is_finished_and_the_row_removed():
    index = FakeVectorIndex(enabled=True, fail_delete=True)
    service, database, _ = build_memory_service(index_client=index)
    written = _write(service, "req-r-4")
    with bound_context(**IDENTITY):
        assert service.delete_memory(written["memory_id"])["status"] == "partial"

    index.fail_delete = False
    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    assert report["drift"]["tombstone_vector"] == 1
    assert report["repaired"] == 1
    assert database["episodic_memories"].docs == []
    assert index.deleted_ids[-1] == written["memory_id"]


def test_a_superseded_memory_that_kept_its_point_stops_owing_the_index():
    index = FakeVectorIndex(enabled=True, fail_delete=True)
    service, database, _ = build_memory_service(index_client=index)
    original = _write(service, "req-r-5")
    replacement = episodic_candidate("The user cancelled the beta milestone.")
    replacement["supersedes"] = original["memory_id"]
    with bound_context(**IDENTITY):
        service.write_memory(replacement, {"owner_type": "user", "request_id": "req-r-6"})

    index.fail_delete = False
    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    retired = next(doc for doc in database["episodic_memories"].docs if doc["id"] == original["memory_id"])
    assert report["drift"]["tombstone_vector"] == 1
    # History is kept: the row survives, it simply no longer has a vector.
    assert retired["status"] == "superseded"
    assert retired["retrieval"]["embedding_status"] == "disabled"


def test_a_point_whose_memory_is_gone_is_removed_from_the_index():
    index = FakeVectorIndex(
        enabled=True,
        points=[{"point_id": "point-orphan", "payload": {"memory_id": "memory-that-no-longer-exists"}}],
    )
    service, _, _ = build_memory_service(index_client=index)

    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    assert report["drift"]["orphan_vector"] == 1
    assert report["repaired"] == 1
    assert index.deleted_point_ids == ["point-orphan"]


def test_a_second_point_claiming_one_memory_is_removed():
    index = FakeVectorIndex(enabled=True)
    service, _, _ = build_memory_service(index_client=index)
    written = _write(service, "req-r-7")
    memory_id = written["memory_id"]
    index.points = [
        {
            "point_id": index.point_id("tenant-a", "user-1", memory_id),
            "payload": {"memory_id": memory_id},
        },
        {"point_id": "legacy-point-id", "payload": {"memory_id": memory_id}},
    ]

    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    assert report["drift"]["duplicate_vector"] == 1
    # The point built by the current deterministic scheme is the one kept.
    assert index.deleted_point_ids == ["legacy-point-id"]


def test_reconciling_consistent_state_reports_no_drift_and_changes_nothing():
    service, database, _ = _live_service()
    _write(service, "req-r-8")
    before = [dict(doc) for doc in database["episodic_memories"].docs]

    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    assert report["status"] == "success"
    assert report["repaired"] == 0
    assert sum(report["drift"].values()) == 0
    assert database["episodic_memories"].docs == before


def test_a_second_reconciliation_pass_repairs_nothing_further():
    index = FakeVectorIndex(enabled=True)
    embedding = FakeEmbeddingClient(fail=True)
    service, _, _ = build_memory_service(index_client=index, embedding_client=embedding)
    _write(service, "req-r-9")
    embedding.fail = False

    with bound_context(**IDENTITY):
        reconciler = build_reconciliation_service(service)
        first = reconciler.reconcile()
        second = reconciler.reconcile()

    assert first["repaired"] == 1
    assert second["repaired"] == 0
    assert sum(second["drift"].values()) == 0


def test_one_pass_is_bounded_by_its_limit_and_resumes_on_the_next():
    index = FakeVectorIndex(enabled=True)
    embedding = FakeEmbeddingClient(fail=True)
    service, _, _ = build_memory_service(index_client=index, embedding_client=embedding)
    for number in range(5):
        _write(service, f"req-r-bound-{number}", text=f"Milestone number {number} was reached.")
    embedding.fail = False

    with bound_context(**IDENTITY):
        reconciler = build_reconciliation_service(service)
        first = reconciler.reconcile(limit=2)
        second = reconciler.reconcile(limit=2)

    assert first["repaired"] == 2
    assert second["repaired"] == 2
    assert first["scanned"] == 5


def test_reconciliation_repairs_only_the_callers_own_tenant():
    service, database, _ = _live_service()
    _write(service, "req-r-10", identity=IDENTITY)
    _write(service, "req-r-11", identity=OTHER_TENANT)
    for doc in database["episodic_memories"].docs:
        doc["retrieval"]["embedding_status"] = "pending"

    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    repaired = [
        doc for doc in database["episodic_memories"].docs
        if doc["retrieval"]["embedding_status"] == "indexed"
    ]
    assert report["repaired"] == 1
    assert [doc["tenant_id"] for doc in repaired] == ["tenant-a"]


def test_reconciliation_is_a_skip_rather_than_a_clean_run_when_there_is_no_index():
    service, _, _ = build_memory_service(index_client=FakeVectorIndex(enabled=False))
    _write(service, "req-r-12")

    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).reconcile()

    assert report["status"] == "skipped"
    assert report["index_enabled"] is False


def test_the_drift_report_names_what_owes_repair_without_repairing_it():
    index = FakeVectorIndex(enabled=True)
    embedding = FakeEmbeddingClient(fail=True)
    service, database, _ = build_memory_service(index_client=index, embedding_client=embedding)
    written = _write(service, "req-r-13")

    with bound_context(**IDENTITY):
        report = build_reconciliation_service(service).drift_report()

    assert report["pending_count"] == 1
    assert report["pending"][0]["memory_id"] == written["memory_id"]
    assert report["pending"][0]["embedding_status"] == "failed"
    assert index.indexed_ids == []
    assert database["episodic_memories"].docs[0]["retrieval"]["embedding_status"] == "failed"
