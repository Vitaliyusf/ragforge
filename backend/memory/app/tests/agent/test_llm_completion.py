"""The utility LLM call behind exit summaries: what it sends, and how it fails."""

from unittest.mock import Mock

import httpx

from app.services.chat_exit_service import ChatExitService, _normalize_vllm_base_url


def test_normalize_vllm_base_url_accepts_root_or_v1():
    assert _normalize_vllm_base_url("http://vllm:8000") == "http://vllm:8000/v1"
    assert _normalize_vllm_base_url("http://vllm:8000/v1") == "http://vllm:8000/v1"
    assert _normalize_vllm_base_url("") == "http://vllm:8000/v1"


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


def test_request_llm_completion_disables_reasoning_for_utility_calls(monkeypatch):
    """Qwen3-style reasoning models return null content unless thinking is off."""
    captured = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": "A headline"}}]}

    class _FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            captured.update(json)
            return _FakeResponse()

    monkeypatch.setattr("app.services.chat_exit_service.httpx.Client", _FakeClient)

    service = ChatExitService(Mock(), Mock(), Mock(), Mock())
    service._request_llm_completion("Name this conversation")

    assert captured["chat_template_kwargs"] == {"enable_thinking": False}


def test_request_llm_completion_strips_leaked_reasoning(monkeypatch):
    """Any leaked <think> block is removed before the text is returned."""
    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": "<think>hmm</think>Beta launch"}}]}

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

    assert service._request_llm_completion("Name this") == "Beta launch"


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
