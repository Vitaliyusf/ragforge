"""Unit tests for the generate_title action in the RabbitMQ memory handler."""
from unittest.mock import Mock

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
    return handler, chat_exit_service


def test_generate_title_delegates_to_chat_exit_service():
    """The action forwards to ChatExitService.generate_title and returns its result."""
    handler, chat_exit_service = _make_handler()
    chat_exit_service.generate_title.return_value = {"status": "success", "title": "A good name"}

    reply = handler._handle_generate_title({"chat_id": "c1", "action": "generate_title"})

    chat_exit_service.generate_title.assert_called_once_with("c1")
    assert reply["success"] is True
    assert reply["payload"] == {"status": "success", "title": "A good name"}


def test_generate_title_requires_a_chat_id():
    """A missing chat_id is a client error, not a service crash."""
    handler, chat_exit_service = _make_handler()

    reply = handler._handle_generate_title({"action": "generate_title"})

    chat_exit_service.generate_title.assert_not_called()
    assert reply["success"] is False
    assert "chat_id" in reply["error"]["message"]
