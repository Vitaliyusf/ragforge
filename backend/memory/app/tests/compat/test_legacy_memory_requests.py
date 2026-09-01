"""Request shapes and surfaces kept alive for callers written before ownership
came from trusted context.
"""

from unittest.mock import MagicMock, Mock, patch

from app.services.memory_handler_service import MemoryHandlerService
from shared.context import bound_context

from app.tests._memory_harness import (
    build_memory_service,
    episodic_candidate,
)


def test_memory_handler_accepts_legacy_request_without_trusting_owner_fields():
    service, database, logger = build_memory_service()
    handler = MemoryHandlerService(
        chat_service=Mock(),
        message_service=Mock(),
        memory_service=service,
        chat_exit_service=Mock(),
        logger=logger,
    )

    with bound_context(tenant_id="tenant-a", user_id="trusted-owner", role="user"):
        reply = handler.process_request(
            {
                "correlation_id": "corr-legacy",
                "trace_id": "trace-legacy",
                "action": "write_memory",
                "owner_id": "untrusted-owner",
                "owner_type": "conversation",
                "candidate": episodic_candidate(),
            }
        )

    stored = database["episodic_memories"].docs[0]
    assert stored["owner_id"] == "trusted-owner"
    assert stored["owner_type"] == "user"
    assert stored["tenant_id"] == "tenant-a"
    assert reply["message_type"] == "reply"
    assert reply["source_service"] == "memory"
    assert reply["target_service"] == "unknown"
    assert reply["correlation_id"] == "corr-legacy"
    assert reply["success"] is True
    assert reply["payload"]["status"] == "accepted"


def test_user_insight_surfaces_remain_deprecated_and_non_persistent():
    service, _, _ = build_memory_service()

    created = service.update_user_insight("The user prefers concise answers.")

    assert service.get_user_insight() is None
    assert created["category"] == "user_insight"
    assert created["metadata"]["deprecated"] is True
    assert service.get_all_memories() == []


def test_manual_preference_create_is_explicit_and_retry_returns_canonical_memory():
    service, database, _ = build_memory_service()

    with bound_context(tenant_id="tenant-a", user_id="user-a", role="user"):
        first = service.create_memory(
            "The user prefers concise answers.",
            category="user_preference",
            request_context={"request_id": "manual-create-1"},
        )
        retry = service.create_memory(
            "The user prefers concise answers.",
            category="user_preference",
            request_context={"request_id": "manual-create-2"},
        )

    assert retry["id"] == first["id"]
    assert len(database["semantic_preferences"].docs) == 1
    assert database["semantic_preferences"].docs[0]["provenance"]["explicit_user_signal"] is True
    assert {row["request_id"] for row in database["memory_write_log"].docs} == {
        "manual-create-1",
        "manual-create-2",
    }


def test_delete_does_not_truth_test_a_pymongo_collection():
    service, database, _ = build_memory_service()

    with bound_context(tenant_id="tenant-a", user_id="user-a", role="user"):
        created = service.write_memory(
            episodic_candidate(),
            {"owner_id": "user-a", "owner_type": "user"},
        )
        document = database["episodic_memories"].docs[0]

        collection = MagicMock()
        collection.__bool__.side_effect = NotImplementedError("PyMongo collections have no truth value")
        collection.delete_one.return_value.deleted_count = 1

        with patch.object(service, "_find_memory_document", return_value=(collection, document)):
            deleted = service.delete_memory(created["memory_id"])

    assert deleted["status"] == "deleted"
    collection.delete_one.assert_called_once()
