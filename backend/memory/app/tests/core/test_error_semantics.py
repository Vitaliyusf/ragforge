"""Failure classification contracts for Memory chat and message operations."""

from unittest.mock import Mock

import pytest

from app.core.errors import ChatNotFoundError, DatabaseError, ErrorCode
from app.db.implementations.mongodb import MongoDBChatRepository
from app.services.chat_service import ChatService
from app.services.memory_handler_service import MemoryHandlerService
from app.services.message_service import MessageService


def _chat_service(collection: Mock) -> ChatService:
    service = ChatService(Mock())
    service._get_collection = Mock(return_value=collection)
    return service


def test_add_message_creates_chat_only_for_explicit_not_found() -> None:
    chat_service = Mock(spec=ChatService)
    chat_service.get_chat.side_effect = ChatNotFoundError("missing")
    collection = Mock()
    service = MessageService(Mock(), chat_service)
    service._get_collection = Mock(return_value=collection)

    service.add_message("message-1", "chat-1", "user", "hello")

    chat_service.create_chat.assert_called_once_with("chat-1", "New Chat")


def test_add_message_stores_sanitized_metadata_and_legacy_reads_default_empty() -> None:
    chat_service = Mock(spec=ChatService)
    collection = Mock()
    collection.find.return_value.sort.return_value = [
        {"id": "legacy", "chat_id": "chat-1", "sender": "Assistant", "message": "Old"}
    ]
    service = MessageService(Mock(), chat_service)
    service._get_collection = Mock(return_value=collection)

    service.add_message(
        "message-1",
        "chat-1",
        "Assistant",
        "Answer",
        {
            "turnId": "turn-1",
            "sources": [{"title": "Guide", "text": "private chunk", "text_preview": "excerpt"}],
            "unknown": "drop me",
        },
    )

    stored = collection.insert_one.call_args.args[0]
    assert stored["metadata"] == {
        "turnId": "turn-1",
        "sources": [{"title": "Guide", "text_preview": "excerpt"}],
    }
    assert service.get_messages("chat-1")[0]["metadata"] == {}


def test_memory_handler_forwards_message_metadata() -> None:
    message_service = Mock(spec=MessageService)
    message_service.add_message.return_value = {"id": "message-1"}
    handler = MemoryHandlerService(Mock(), message_service, Mock(), Mock(), Mock())

    reply = handler.process_request({
        "action": "add_message",
        "chat_id": "chat-1",
        "message_id": "message-1",
        "sender": "Assistant",
        "message": "Answer",
        "metadata": {"turnId": "turn-1"},
        "correlation_id": "corr-1",
        "source_service": "gateway",
    })

    message_service.add_message.assert_called_once_with(
        "message-1", "chat-1", "Assistant", "Answer", {"turnId": "turn-1"}
    )
    assert reply["success"] is True


def test_add_message_does_not_create_chat_after_database_lookup_failure() -> None:
    chat_service = Mock(spec=ChatService)
    chat_service.get_chat.side_effect = DatabaseError("Database operation failed")
    service = MessageService(Mock(), chat_service)

    with pytest.raises(DatabaseError) as raised:
        service.add_message("message-1", "chat-1", "user", "hello")

    chat_service.create_chat.assert_not_called()
    assert raised.value.error_code is ErrorCode.DATABASE_ERROR


def test_chat_mutation_distinguishes_noop_from_database_failure() -> None:
    no_op_collection = Mock()
    no_op_collection.update_one.return_value.modified_count = 0
    assert _chat_service(no_op_collection).update_title("chat-1", "Same title") is False

    failed_collection = Mock()
    failed_collection.update_one.side_effect = RuntimeError("db-password=secret")
    with pytest.raises(DatabaseError) as raised:
        _chat_service(failed_collection).update_title("chat-1", "New title")

    assert str(raised.value) == "Database operation failed"
    assert raised.value.details == {"operation": "update_chat_title"}


def test_unavailable_repository_is_database_failure_not_false() -> None:
    repository = MongoDBChatRepository.__new__(MongoDBChatRepository)
    repository._collection = None

    with pytest.raises(DatabaseError) as raised:
        repository.delete("chat-1")

    assert raised.value.error_code is ErrorCode.DATABASE_ERROR


def test_rpc_error_envelope_preserves_category_without_private_cause() -> None:
    chat_service = Mock(spec=ChatService)
    chat_service.get_all_chats.side_effect = DatabaseError(
        "Database operation failed",
        details={"operation": "get_all_chats"},
        original_exception=RuntimeError("db-password=secret"),
    )
    handler = MemoryHandlerService(chat_service, Mock(), Mock(), Mock(), Mock())

    reply = handler.process_request(
        {
            "action": "get_chats",
            "correlation_id": "corr-1",
            "source_service": "gateway",
        }
    )

    assert reply["success"] is False
    assert reply["error"] == {
        "message": "Database operation failed",
        "code": "DATABASE_ERROR",
        "retryable": False,
    }
    assert "secret" not in str(reply)
