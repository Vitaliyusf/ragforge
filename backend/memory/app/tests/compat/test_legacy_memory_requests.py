"""Request shapes and surfaces kept alive for callers written before ownership
came from trusted context.
"""

from unittest.mock import Mock

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
