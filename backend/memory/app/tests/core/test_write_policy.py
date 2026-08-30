"""What may be written to long-term memory, and what is refused."""

from app.tests._memory_harness import (
    FakeEmbeddingClient,
    FakeVectorIndex,
    build_memory_service,
    episodic_candidate,
    preference_candidate,
)


def test_write_memory_accepts_episodic_memory():
    service, database, _ = build_memory_service()

    result = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-1", "trace_id": "trace-1"},
    )

    assert result["status"] == "accepted"
    assert result["memory_class"] == "episodic"
    assert len(database["episodic_memories"].docs) == 1
    assert database["memory_write_log"].docs[0]["status"] == "accepted"


def test_write_memory_accepts_and_upserts_semantic_preference():
    service, database, _ = build_memory_service()

    first = service.write_memory(
        preference_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-2"},
    )
    second = service.write_memory(
        preference_candidate("The user again asked for concise answers with citations."),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-3"},
    )

    assert first["status"] == "accepted"
    assert second["status"] == "merged"
    assert len(database["semantic_preferences"].docs) == 1
    stored = database["semantic_preferences"].docs[0]
    assert stored["preference_key"] == "response_style"
    assert stored["evidence_count"] >= 2


def test_write_memory_rejects_transient_candidates():
    service, database, _ = build_memory_service()

    result = service.write_memory(
        {
            "content": {"text": "The user is currently working on this for now and will revisit next turn."},
            "importance": 0.8,
            "confidence": 0.9,
        },
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-4"},
    )

    assert result["status"] == "rejected"
    assert "temporary task state" in result["reason"]
    assert len(database["episodic_memories"].docs) == 0
    assert database["memory_write_log"].docs[0]["status"] == "rejected"


def test_write_memory_rejects_retrieval_dump_candidates():
    service, database, _ = build_memory_service()

    result = service.write_memory(
        {
            "content": {"text": "page_content: chunk 14 document: retrieval result embedding score=0.93"},
            "importance": 0.8,
            "confidence": 0.9,
        },
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-5"},
    )

    assert result["status"] == "rejected"
    assert "retrieval dumps" in result["reason"]
    assert len(database["memory_write_log"].docs) == 1


def test_write_memory_rejects_hidden_reasoning_candidates():
    service, _, _ = build_memory_service()

    result = service.write_memory(
        {
            "content": {"text": "Internal scratchpad chain of thought about the user's intent."},
            "importance": 0.8,
            "confidence": 0.8,
        },
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-6"},
    )

    assert result["status"] == "rejected"
    assert "hidden reasoning" in result["reason"]


def test_write_memory_reports_reconciliation_when_the_vector_upsert_fails():
    index = FakeVectorIndex(enabled=True, fail_index=True)
    service, database, _ = build_memory_service(index_client=index)

    result = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-10"},
    )

    # MongoDB is canonical, so the memory is stored — but the write result says
    # plainly that the derived index does not have it yet.
    assert result["status"] == "accepted"
    assert result["qdrant_indexed"] is False
    assert result["embedding_status"] == "pending"
    assert result["reconciliation_required"] is True
    assert database["episodic_memories"].docs[0]["retrieval"]["embedding_status"] == "pending"
    assert database["memory_write_log"].docs[0]["qdrant_error"] == "vector upsert failed"


def test_write_memory_reports_reconciliation_when_embedding_is_unavailable():
    index = FakeVectorIndex(enabled=True)
    service, database, _ = build_memory_service(
        index_client=index,
        embedding_client=FakeEmbeddingClient(fail=True),
    )

    result = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-embed-fail"},
    )

    assert result["status"] == "accepted"
    assert result["embedding_status"] == "failed"
    assert result["reconciliation_required"] is True
    # No vector was invented to keep the happy path looking green.
    assert index.indexed_ids == []
    assert database["episodic_memories"].docs[0]["retrieval"]["qdrant_point_id"] is None


def test_write_memory_records_embedding_provenance_on_indexed_memories():
    index = FakeVectorIndex(enabled=True)
    service, database, _ = build_memory_service(
        index_client=index,
        embedding_client=FakeEmbeddingClient(dimensions=8, model="test-e5"),
    )

    result = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-provenance"},
    )

    stored = database["episodic_memories"].docs[0]["retrieval"]
    assert result["reconciliation_required"] is False
    assert stored["embedding_status"] == "indexed"
    assert stored["embedding_model"] == "test-e5"
    assert stored["embedding_dimensions"] == 8
    assert stored["vector_collection"] == "memory_items_test"
    assert stored["vector_synced_at"]


def test_write_memory_rejects_an_exact_duplicate_of_an_active_memory():
    service, database, _ = build_memory_service()

    first = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-dup-1"},
    )
    duplicate = service.write_memory(
        episodic_candidate("  the USER launched the beta milestone.  "),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-dup-2"},
    )

    assert first["status"] == "accepted"
    assert duplicate["status"] == "duplicate"
    assert duplicate["memory_id"] == first["memory_id"]
    assert len(database["episodic_memories"].docs) == 1
