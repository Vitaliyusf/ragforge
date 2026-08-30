"""What a redelivered memory command may and may not do.

A queue that guarantees at-least-once delivery will eventually deliver every
write twice, and a retry that arrives after the original already succeeded is
the normal case, not the exotic one. None of it may produce a second copy of a
fact, a second vector, a divergent revision, or — worst of all — a memory the
owner already deleted.
"""

import pytest

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


def _live_service():
    return build_memory_service(
        index_client=InMemoryVectorIndex(),
        embedding_client=BagOfWordsEmbeddingClient(),
    )


def _write(service, request_id, text="The user launched the beta milestone."):
    with bound_context(**IDENTITY):
        return service.write_memory(
            episodic_candidate(text),
            {"owner_type": "user", "request_id": request_id},
        )


def test_a_redelivered_write_returns_the_first_outcome_and_stores_nothing_new():
    service, database, _ = _live_service()

    first = _write(service, "req-i-1")
    second = _write(service, "req-i-1")

    assert first["memory_id"] == second["memory_id"]
    assert second["status"] == first["status"]
    assert len(database["episodic_memories"].docs) == 1
    assert database["episodic_memories"].docs[0]["revision"] == 1


def test_a_write_repeated_under_a_new_request_id_is_still_only_one_memory():
    service, database, _ = _live_service()

    first = _write(service, "req-i-2")
    second = _write(service, "req-i-3")

    # Different delivery, same fact: idempotency keys catch the retry, and
    # content identity catches the genuine repeat.
    assert second["status"] == "duplicate"
    assert second["memory_id"] == first["memory_id"]
    assert len(database["episodic_memories"].docs) == 1


def test_a_redelivered_write_does_not_index_a_second_vector():
    index = InMemoryVectorIndex()
    service, _, _ = build_memory_service(
        index_client=index,
        embedding_client=BagOfWordsEmbeddingClient(),
    )

    _write(service, "req-i-4")
    _write(service, "req-i-4")

    assert len(index.points) == 1


def test_a_retry_after_a_delete_does_not_resurrect_the_memory():
    service, database, _ = _live_service()
    written = _write(service, "req-i-5")
    with bound_context(**IDENTITY):
        service.delete_memory(written["memory_id"])

    replay = _write(service, "req-i-5")

    assert database["episodic_memories"].docs == []
    assert replay["memory_id"] == written["memory_id"]
    with bound_context(**IDENTITY):
        with pytest.raises(ValueError):
            service.get_memory(written["memory_id"])


def test_a_replayed_write_reports_the_reconciliation_state_it_actually_left():
    index = FakeVectorIndex(enabled=True)
    embedding = FakeEmbeddingClient(fail=True)
    service, _, _ = build_memory_service(index_client=index, embedding_client=embedding)

    first = _write(service, "req-i-6")
    replay = _write(service, "req-i-6")

    # The retry must not launder a pending sync into an apparent success.
    assert first["reconciliation_required"] is True
    assert replay["reconciliation_required"] is True
    assert replay["embedding_status"] == "failed"


def test_a_supersession_delivered_twice_retires_one_memory_once():
    service, database, _ = _live_service()
    original = _write(service, "req-i-7")
    replacement = episodic_candidate("The user cancelled the beta milestone.")
    replacement["supersedes"] = original["memory_id"]

    with bound_context(**IDENTITY):
        first = service.write_memory(replacement, {"owner_type": "user", "request_id": "req-i-8"})
        second = service.write_memory(replacement, {"owner_type": "user", "request_id": "req-i-8"})

    docs = database["episodic_memories"].docs
    retired = next(doc for doc in docs if doc["id"] == original["memory_id"])
    assert first["memory_id"] == second["memory_id"]
    assert len(docs) == 2
    assert retired["status"] == "superseded"
    assert retired["superseded_by"] == first["memory_id"]


def test_reconciliation_after_a_restart_completes_a_half_finished_write():
    # The first process wrote the canonical row and died before the index
    # heard about it. A fresh service over the same storage — the shape a
    # restart takes — has to be able to finish the job.
    index = FakeVectorIndex(enabled=True)
    embedding = FakeEmbeddingClient(fail=True)
    service, database, _ = build_memory_service(index_client=index, embedding_client=embedding)
    written = _write(service, "req-i-9")

    restarted, _, _ = build_memory_service(
        index_client=index,
        embedding_client=FakeEmbeddingClient(),
    )
    restarted._db_provider = lambda: database
    with bound_context(**IDENTITY):
        report = build_reconciliation_service(restarted).reconcile()

    assert report["repaired"] == 1
    assert index.indexed_ids == [written["memory_id"]]
    assert database["episodic_memories"].docs[0]["retrieval"]["embedding_status"] == "indexed"


def test_a_delete_retried_after_the_vector_finally_went_stays_deleted():
    index = FakeVectorIndex(enabled=True, fail_delete=True)
    service, database, _ = build_memory_service(index_client=index)
    written = _write(service, "req-i-10")

    with bound_context(**IDENTITY):
        partial = service.delete_memory(written["memory_id"])
        index.fail_delete = False
        report = build_reconciliation_service(service).reconcile()
        # A late retry of the same delete finds nothing left to remove.
        with pytest.raises(ValueError):
            service.delete_memory(written["memory_id"])

    assert partial["status"] == "partial"
    assert report["repaired"] == 1
    assert database["episodic_memories"].docs == []
