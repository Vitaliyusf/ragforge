"""Lifecycle transitions a memory may make, and what each one hides."""

import pytest

from app.tests._memory_harness import (
    FakeVectorIndex,
    build_memory_service,
    episodic_candidate,
    preference_candidate,
)


def test_new_memory_starts_active_at_revision_one():
    service, database, _ = build_memory_service()

    result = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-1"},
    )

    stored = database["episodic_memories"].docs[0]
    assert result["status"] == "accepted"
    assert stored["status"] == "active"
    assert stored["revision"] == 1
    assert stored["superseded_by"] is None


def test_superseding_candidate_leaves_exactly_one_active_memory():
    service, database, _ = build_memory_service()
    original = service.write_memory(
        episodic_candidate("The user shipped the beta on the first of March."),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-2"},
    )

    replacement = dict(episodic_candidate("The user shipped the beta on the third of March."))
    replacement["supersedes"] = original["memory_id"]
    result = service.write_memory(
        replacement,
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-3"},
    )

    docs = {doc["id"]: doc for doc in database["episodic_memories"].docs}
    assert result["superseded_memory_id"] == original["memory_id"]
    assert docs[original["memory_id"]]["status"] == "superseded"
    assert docs[original["memory_id"]]["superseded_by"] == result["memory_id"]
    assert docs[result["memory_id"]]["status"] == "active"
    assert [doc["id"] for doc in database["episodic_memories"].docs if doc["status"] == "active"] == [
        result["memory_id"]
    ]


def test_superseded_memory_is_not_returned_as_a_current_fact():
    service, _, _ = build_memory_service()
    original = service.write_memory(
        episodic_candidate("The user shipped the beta on the first of March."),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-4"},
    )
    replacement = dict(episodic_candidate("The user shipped the beta on the third of March."))
    replacement["supersedes"] = original["memory_id"]
    service.write_memory(
        replacement,
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-5"},
    )

    result = service.get_relevant_memories(
        {"owner_id": "owner-1", "owner_type": "user", "text": "beta shipped", "limit": 5}
    )

    returned = [memory["content"]["text"] for memory in result["memories"]]
    assert returned == ["The user shipped the beta on the third of March."]


def test_updating_a_preference_replaces_its_value_in_place():
    service, database, _ = build_memory_service()
    service.write_memory(
        preference_candidate("The user explicitly prefers concise answers with citations."),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-6"},
    )
    extended = dict(preference_candidate("The user now explicitly prefers extended answers."))
    extended["value"] = "extended"
    service.write_memory(
        extended,
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-7"},
    )

    stored = database["semantic_preferences"].docs
    assert len(stored) == 1
    assert stored[0]["value"] == "extended"
    assert stored[0]["revision"] == 2
    assert stored[0]["status"] == "active"


def test_update_memory_bumps_revision_and_marks_the_vector_stale():
    index = FakeVectorIndex(enabled=True)
    service, database, _ = build_memory_service(index_client=index)
    written = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-8"},
    )

    service.update_memory(written["memory_id"], content="The user cancelled the beta milestone.")

    stored = database["episodic_memories"].docs[0]
    assert stored["revision"] == 2
    assert stored["content"]["text"] == "The user cancelled the beta milestone."
    # The text changed, so the memory was embedded again rather than keeping a
    # vector that describes the previous wording.
    assert index.indexed_ids == [written["memory_id"], written["memory_id"]]


def test_delete_removes_the_memory_from_storage_and_from_the_index():
    index = FakeVectorIndex(enabled=True)
    service, database, _ = build_memory_service(index_client=index)
    written = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-9"},
    )

    result = service.delete_memory(written["memory_id"])

    assert result["status"] == "deleted"
    assert result["vector_deleted"] is True
    assert result["reconciliation_required"] is False
    assert index.deleted_ids == [written["memory_id"]]
    assert database["episodic_memories"].docs == []


def test_delete_keeps_a_tombstone_when_the_vector_point_survives():
    index = FakeVectorIndex(enabled=True, fail_delete=True)
    service, database, _ = build_memory_service(index_client=index)
    written = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-10"},
    )

    result = service.delete_memory(written["memory_id"])

    # The delete is reported as partial, not as success, and the canonical row
    # survives as a tombstone so reconciliation can still find the point id.
    assert result["status"] == "partial"
    assert result["vector_deleted"] is False
    assert result["reconciliation_required"] is True
    assert database["episodic_memories"].docs[0]["status"] == "deleted"
    assert database["episodic_memories"].docs[0]["retrieval"]["embedding_status"] == "delete_pending"


def test_tombstoned_memory_is_invisible_to_every_read_path():
    index = FakeVectorIndex(enabled=True, fail_delete=True)
    service, _, _ = build_memory_service(index_client=index)
    written = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-life-11"},
    )
    service.delete_memory(written["memory_id"])

    retrieved = service.get_relevant_memories(
        {"owner_id": "owner-1", "owner_type": "user", "text": "beta milestone", "limit": 5}
    )

    assert retrieved["memories"] == []
    assert service.get_all_memories() == []
    assert service.list_memory_for_debug({"owner_id": "owner-1"})["memories"] == []
    with pytest.raises(ValueError):
        service.get_memory(written["memory_id"])


def test_deleting_an_unknown_memory_is_an_explicit_error():
    service, _, _ = build_memory_service()

    with pytest.raises(ValueError):
        service.delete_memory("does-not-exist")
