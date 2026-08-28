"""What may be written to long-term memory, and what is refused."""

from app.tests._memory_harness import (
    FakeQdrantIndex,
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


def test_write_memory_preserves_accepted_status_when_qdrant_fails():
    index = FakeQdrantIndex(enabled=True, fail_index=True)
    service, database, _ = build_memory_service(index_client=index)

    result = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-10"},
    )

    assert result["status"] == "accepted"
    assert result["qdrant_indexed"] is False
    assert database["episodic_memories"].docs[0]["retrieval"]["embedding_status"] == "failed"
    assert database["memory_write_log"].docs[0]["qdrant_error"] == "qdrant indexing failed"
