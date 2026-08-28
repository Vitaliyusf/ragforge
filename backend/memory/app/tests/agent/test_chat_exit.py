"""Ending a chat: the headline, the summary and naming an untitled chat."""

from unittest.mock import Mock

from app.services.chat_exit_service import ChatExitService


def test_process_chat_exit_uses_local_llm_helper_for_headline_and_summary():
    chat_service = Mock()
    chat_service.get_chat.return_value = {"id": "chat-1", "title": "New Chat"}
    message_service = Mock()
    message_service.get_messages.return_value = [
        {"sender": "User", "message": "We launched the beta today."},
        {"sender": "Assistant", "message": "I will remember the launch milestone."},
    ]
    memory_service = Mock()
    logger = Mock()

    service = ChatExitService(chat_service, message_service, memory_service, logger)
    service._memory_agent = Mock()
    service._request_llm_completion = Mock(side_effect=["Beta launch", "Summary text"])

    result = service.process_chat_exit("chat-1")

    assert result == {"status": "success", "headline": "Beta launch", "memories_updated": True}
    chat_service.update_title.assert_called_once_with("chat-1", "Beta launch")
    chat_service.update_compressed_summary.assert_called_once_with("chat-1", "Summary text")
    service._memory_agent.run.assert_called_once()
    assert service._request_llm_completion.call_count == 2


def test_generate_title_names_an_untitled_chat():
    chat_service = Mock()
    chat_service.get_chat.return_value = {"id": "chat-1", "title": "New Chat"}
    message_service = Mock()
    message_service.get_messages.return_value = [
        {"sender": "User", "message": "How do I rotate the signing keys?"},
        {"sender": "Assistant", "message": "Use the rotate-keys runbook."},
    ]

    service = ChatExitService(chat_service, message_service, Mock(), Mock())
    service._request_llm_completion = Mock(return_value="Rotating signing keys")

    result = service.generate_title("chat-1")

    assert result == {"status": "success", "title": "Rotating signing keys"}
    chat_service.update_title.assert_called_once_with("chat-1", "Rotating signing keys")


def test_generate_title_is_a_noop_once_a_chat_is_named():
    chat_service = Mock()
    chat_service.get_chat.return_value = {"id": "chat-1", "title": "Rotating signing keys"}
    message_service = Mock()
    message_service.get_messages.return_value = [
        {"sender": "User", "message": "another question"},
    ]

    service = ChatExitService(chat_service, message_service, Mock(), Mock())
    service._request_llm_completion = Mock()

    result = service.generate_title("chat-1")

    assert result == {"status": "success", "title": "Rotating signing keys"}
    chat_service.update_title.assert_not_called()
    service._request_llm_completion.assert_not_called()


def test_generate_title_skips_empty_conversations():
    chat_service = Mock()
    chat_service.get_chat.return_value = {"id": "chat-1", "title": "New Chat"}
    message_service = Mock()
    message_service.get_messages.return_value = []

    service = ChatExitService(chat_service, message_service, Mock(), Mock())
    service._request_llm_completion = Mock()

    result = service.generate_title("chat-1")

    assert result == {"status": "success", "title": None}
    chat_service.update_title.assert_not_called()
    service._request_llm_completion.assert_not_called()
