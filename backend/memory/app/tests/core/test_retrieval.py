"""Owner-scoped retrieval and the episodic/semantic balance it returns."""

from app.tests._memory_harness import (
    FakeQdrantIndex,
    build_memory_service,
    episodic_candidate,
    preference_candidate,
)


def test_get_relevant_memories_returns_owner_scoped_results_and_excludes_archived():
    service, database, _ = build_memory_service()
    episodic = episodic_candidate()
    semantic = preference_candidate()

    accepted = service.write_memory(episodic, {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-7"})
    service.write_memory(semantic, {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-8"})
    service.write_memory(episodic_candidate("Another owner's milestone"), {"owner_id": "owner-2", "owner_type": "user", "request_id": "req-9"})

    archived_id = accepted["memory_id"]
    database["episodic_memories"].update_one({"id": archived_id}, {"$set": {"archived_at": "2026-03-18T00:00:00+00:00"}})

    result = service.get_relevant_memories(
        {
            "owner_id": "owner-1",
            "owner_type": "user",
            "text": "Please stay concise and use citations.",
            "limit": 5,
        }
    )

    assert all(item["owner_id"] == "owner-1" for item in result["memories"])
    assert all(item["archived_at"] is None for item in result["memories"])
    assert len(result["memories"]) == 1
    assert result["memories"][0]["memory_class"] == "semantic_preference"


def test_get_relevant_memories_balances_episodic_and_semantic_preference():
    index = FakeQdrantIndex(
        enabled=True,
        search_results=[
            {"memory_id": "episodic-1", "score": 0.95},
            {"memory_id": "pref-1", "score": 0.94},
            {"memory_id": "pref-2", "score": 0.93},
            {"memory_id": "pref-3", "score": 0.92},
        ],
    )
    service, database, _ = build_memory_service(index_client=index)

    database["episodic_memories"].insert_one(
        {
            "id": "episodic-1",
            "owner_id": "owner-1",
            "owner_type": "user",
            "memory_class": "episodic",
            "content": {"text": "The user launched the beta.", "summary": "Beta launch"},
            "source": "manual",
            "confidence": 0.9,
            "importance": 0.8,
            "tags": ["launch"],
            "created_at": "2026-03-01T00:00:00+00:00",
            "updated_at": "2026-03-17T12:00:00+00:00",
            "last_accessed_at": None,
            "archived_at": None,
            "provenance": {"explicit_user_signal": True},
            "retrieval": {"keywords": ["launch", "beta"], "embedding_status": "indexed", "qdrant_point_id": "episodic-1"},
            "event_at": "2026-03-01T00:00:00+00:00",
            "expires_at": None,
            "stability": 0.9,
        }
    )
    for idx in range(1, 4):
        database["semantic_preferences"].insert_one(
            {
                "id": f"pref-{idx}",
                "owner_id": "owner-1",
                "owner_type": "user",
                "memory_class": "semantic_preference",
                "content": {"text": f"Preference {idx}", "summary": f"Preference {idx}"},
                "source": "manual",
                "confidence": 0.9,
                "importance": 0.7,
                "tags": ["preference"],
                "created_at": "2026-03-01T00:00:00+00:00",
                "updated_at": "2026-03-17T12:00:00+00:00",
                "last_accessed_at": None,
                "archived_at": None,
                "provenance": {"explicit_user_signal": True},
                "retrieval": {"keywords": ["preference", str(idx)], "embedding_status": "indexed", "qdrant_point_id": f"pref-{idx}"},
                "preference_key": f"pref-key-{idx}",
                "value": "value",
                "value_type": "string",
                "strength": 0.9,
                "evidence_count": 3,
            }
        )

    result = service.get_relevant_memories(
        {"owner_id": "owner-1", "owner_type": "user", "text": "launch preferences", "limit": 4}
    )

    classes = [item["memory_class"] for item in result["memories"]]
    assert "episodic" in classes
    assert classes.count("semantic_preference") <= 2


def test_retrieval_honors_owner_id_and_owner_type():
    service, _, _ = build_memory_service()
    service.write_memory(episodic_candidate(), {"owner_id": "session-1", "owner_type": "session", "request_id": "req-11"})
    service.write_memory(episodic_candidate("Conversation memory"), {"owner_id": "conv-1", "owner_type": "conversation", "request_id": "req-12"})

    result = service.get_relevant_memories(
        {"owner_id": "conv-1", "owner_type": "conversation", "text": "Conversation memory", "limit": 5}
    )

    assert len(result["memories"]) == 1
    assert result["memories"][0]["owner_type"] == "conversation"
    assert result["memories"][0]["owner_id"] == "conv-1"
