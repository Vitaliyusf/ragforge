"""Unit tests for delete_chat resilience in the RabbitMQ memory handler."""
from unittest.mock import Mock

from app.core.errors import ChatNotFoundError
from app.services.chat_exit_service import ChatExitService
from app.services.chat_service import ChatService
from app.services.memory_service import LongTermMemoryService
from app.services.message_service import MessageService
from app.services.memory_handler_service import MemoryHandlerService


def _make_handler():
    """Build a handler wired to mocked collaborators."""
    chat_service = Mock(spec=ChatService)
    message_service = Mock(spec=MessageService)
    memory_service = Mock(spec=LongTermMemoryService)
    chat_exit_service = Mock(spec=ChatExitService)
    logger = Mock()
    handler = MemoryHandlerService(
        chat_service, message_service, memory_service, chat_exit_service, logger
    )
    return handler, chat_service, message_service, memory_service


def test_delete_chat_continues_when_memory_cleanup_fails():
    """A failing memory/index backend must not prevent the chat from deleting."""
    handler, chat_service, message_service, memory_service = _make_handler()
    memory_service.delete_memories_by_chat_id.side_effect = RuntimeError("qdrant down")

    reply = handler._handle_delete_chat({"chat_id": "c1", "action": "delete_chat"})

    # The chat (and its messages) are still deleted despite the memory failure.
    message_service.delete_messages_by_chat.assert_called_once_with("c1")
    chat_service.delete_chat.assert_called_once_with("c1")
    assert reply["success"] is True
    assert reply["payload"]["status"] == "success"


def test_delete_chat_is_idempotent_when_chat_absent():
    """Re-deleting an already-removed chat reports success, not an error."""
    handler, chat_service, message_service, memory_service = _make_handler()
    memory_service.delete_memories_by_chat_id.return_value = 0
    chat_service.delete_chat.side_effect = ChatNotFoundError("gone")

    reply = handler._handle_delete_chat({"chat_id": "c1", "action": "delete_chat"})

    assert reply["success"] is True
    assert reply["payload"]["status"] == "success"
