"""Tests for chat-exit title and summary orchestration."""
from __future__ import annotations

from unittest.mock import Mock

import httpx

from app.agent.memory_agent import MemoryAgent
from app.services.chat_exit_service import ChatExitService, _normalize_vllm_base_url


def test_normalize_vllm_base_url_accepts_root_or_v1():
    assert _normalize_vllm_base_url("http://vllm:8000") == "http://vllm:8000/v1"
    assert _normalize_vllm_base_url("http://vllm:8000/v1") == "http://vllm:8000/v1"
    assert _normalize_vllm_base_url("") == "http://vllm:8000/v1"


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


def test_request_llm_completion_returns_first_message_content(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Generated headline"}}]}

    class _FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            assert url.endswith("/chat/completions")
            assert json["model"]
            assert headers["Authorization"].startswith("Bearer ")
            return _FakeResponse()

    monkeypatch.setattr("app.services.chat_exit_service.httpx.Client", _FakeClient)

    service = ChatExitService(Mock(), Mock(), Mock(), Mock())

    assert service._request_llm_completion("Name this conversation") == "Generated headline"


def test_request_llm_completion_raises_when_llm_returns_no_choices(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": []}

    class _FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            return _FakeResponse()

    monkeypatch.setattr("app.services.chat_exit_service.httpx.Client", _FakeClient)

    service = ChatExitService(Mock(), Mock(), Mock(), Mock())

    try:
        service._request_llm_completion("This should fail")
    except RuntimeError as exc:
        assert "No completion choices" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when the LLM returned no choices")


def test_request_llm_completion_raises_runtime_error_on_timeout(monkeypatch):
    class _FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("app.services.chat_exit_service.httpx.Client", _FakeClient)

    service = ChatExitService(Mock(), Mock(), Mock(), Mock())

    try:
        service._request_llm_completion("This should time out")
    except RuntimeError as exc:
        assert "timed out" in str(exc).lower()
    else:
        raise AssertionError("Expected RuntimeError when the chat-exit LLM timed out")


def test_memory_agent_extract_summary_supports_langchain_message_objects():
    class _Message:
        def __init__(self, content):
            self.content = content

    summary = MemoryAgent._extract_summary({"messages": [_Message("Curated memory summary")]})

    assert summary == "Curated memory summary"


def test_memory_agent_extract_summary_supports_list_content_blocks():
    class _Message:
        def __init__(self, content):
            self.content = content

    summary = MemoryAgent._extract_summary(
        {"messages": [_Message([{"text": "Curated "}, {"text": "memory summary"}])]}
    )

    assert summary == "Curated memory summary"
