"""Ending a chat: the headline, the summary and naming an untitled chat."""

from types import SimpleNamespace
from unittest.mock import Mock

from app.services.chat_exit_service import ChatExitService


def test_process_chat_exit_uses_typed_llm_requests_for_all_model_work(monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_exit_service.current_identity",
        lambda: SimpleNamespace(tenant_id="tenant-1", user_id="user-1", role="user"),
    )
    chat_service = Mock()
    chat_service.get_chat.return_value = {"id": "chat-1", "title": "New Chat"}
    message_service = Mock()
    message_service.get_messages.return_value = [
        {"sender": "User", "message": "We launched the beta today."},
        {"sender": "Assistant", "message": "I will remember the launch milestone."},
    ]
    memory_service = Mock()
    memory_service.get_relevant_memories.return_value = {"memories": []}
    logger = Mock()

    service = ChatExitService(chat_service, message_service, memory_service, logger)
    service._request_typed_llm = Mock(
        side_effect=[
            {"title": "Beta launch"},
            {"actions": [], "summary": "No memory changes"},
            {"summary": "Summary text"},
        ]
    )

    result = service.process_chat_exit(
        "chat-1",
        {
            "tenant_id": "tenant-1",
            "owner_id": "user-1",
            "role": "user",
            "request_id": "req-1",
            "trace_id": "trace-1",
        },
    )

    assert result == {
        "status": "success",
        "headline": "Beta launch",
        "memories_updated": False,
        "memory_agent_status": "success",
    }
    chat_service.update_title.assert_called_once_with("chat-1", "Beta launch")
    chat_service.update_compressed_summary.assert_called_once_with("chat-1", "Summary text")
    assert [call.args[0] for call in service._request_typed_llm.call_args_list] == [
        "chat_title",
        "memory_curation",
        "chat_summary",
    ]


def test_generate_title_names_an_untitled_chat():
    chat_service = Mock()
    chat_service.get_chat.return_value = {"id": "chat-1", "title": "New Chat"}
    message_service = Mock()
    message_service.get_messages.return_value = [
        {"sender": "User", "message": "How do I rotate the signing keys?"},
        {"sender": "Assistant", "message": "Use the rotate-keys runbook."},
    ]

    service = ChatExitService(chat_service, message_service, Mock(), Mock())
    service._request_typed_llm = Mock(return_value={"title": "Rotating signing keys"})

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
    service._request_typed_llm = Mock()

    result = service.generate_title("chat-1")

    assert result == {"status": "success", "title": "Rotating signing keys"}
    chat_service.update_title.assert_not_called()
    service._request_typed_llm.assert_not_called()


def test_generate_title_skips_empty_conversations():
    chat_service = Mock()
    chat_service.get_chat.return_value = {"id": "chat-1", "title": "New Chat"}
    message_service = Mock()
    message_service.get_messages.return_value = []

    service = ChatExitService(chat_service, message_service, Mock(), Mock())
    service._request_typed_llm = Mock()

    result = service.generate_title("chat-1")

    assert result == {"status": "success", "title": None}
    chat_service.update_title.assert_not_called()
    service._request_typed_llm.assert_not_called()
