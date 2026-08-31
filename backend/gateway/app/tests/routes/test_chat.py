"""Tests for chat endpoints."""
import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.core.constants import MemoryAction
from app.core.deps import get_chat_service
from app.rest.v1 import chat as chat_routes
from shared.auth import AuthIdentity
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService


def build_chat_app(mock_service):
    """Create a lightweight app for chat route tests."""
    app = FastAPI()
    app.include_router(chat_routes.router, prefix="/v1")
    app.dependency_overrides[get_chat_service] = lambda: mock_service
    app.dependency_overrides[get_current_user] = lambda: AuthIdentity(
        tenant_id="tenant-a", user_id="user-a", role="user", admin_id="admin-a"
    )
    return app


def test_chat_endpoint_with_dependency_override():
    """Test chat endpoint with mocked service dependency."""
    service = MagicMock()
    service.process_chat = AsyncMock(return_value={"response": "Test response"})
    app = build_chat_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            json={
                "message": "Hello",
                "use_rag": False,
                "model": None,
            },
        )

    assert response.status_code == 200
    assert response.json() == {"response": "Test response"}


def test_chat_request_schema():
    """Test chat request schema validation."""
    request = ChatRequest(message="Hello", use_rag=False)
    assert request.message == "Hello"
    assert request.use_rag is False
    assert request.model is None


def test_chat_request_schema_with_model():
    """Test chat request schema with model."""
    request = ChatRequest(message="Hello", use_rag=True, model="gpt-4")
    assert request.message == "Hello"
    assert request.use_rag is True
    assert request.model == "gpt-4"


def test_plain_chat_uses_typed_llm_contract_and_normalizes_reply():
    rpc_client = MagicMock()
    rpc_client.send_request = AsyncMock(
        side_effect=[
            {"status": "success", "insight": ""},
            {
                "status": "success",
                "model": "test-model",
                "raw_output": "OK",
                "parsed_output": {"answer": "OK"},
            },
        ]
    )
    logger = MagicMock()
    config = MagicMock()
    config.short_timeout = 10.0
    config.default_timeout = 120.0
    config.request_topics = {"memory": "memory", "llm_agent": "llm_agent"}
    service = ChatService(rpc_client, logger, config)

    result = asyncio.run(service.process_chat(ChatRequest(message="Reply with OK")))

    llm_call = rpc_client.send_request.await_args_list[1]
    assert llm_call.args[0] == "llm_agent"
    assert llm_call.args[1]["action"] == "answer_generation"
    assert llm_call.args[1]["request_type"] == "answer_generation"
    assert llm_call.args[1]["input"]["question"] == "Reply with OK"
    assert result["response"] == "OK"
    assert "visible_reasoning_steps" not in result


def test_prepare_context_overlaps_reads_and_assembles_deterministically():
    service = object.__new__(ChatService)
    both_started = asyncio.Event()
    started = set()

    async def mark_started(branch):
        started.add(branch)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.1)

    async def fetch_insight():
        await mark_started("insight")
        await asyncio.sleep(0.02)
        return "insight"

    async def fetch_history(_request):
        await mark_started("history")
        return "history", "history"

    service._fetch_user_insight = fetch_insight
    service._fetch_history = fetch_history

    result = asyncio.run(
        service._prepare_context(ChatRequest(message="hello", chat_id="chat-1"))
    )

    assert result == ("insight", "history", "history")


def test_prepare_context_preserves_optional_timeout_fallback():
    rpc_client = MagicMock()

    async def send_request(_routing_key, payload, timeout):
        del timeout
        if payload["action"] == MemoryAction.GET_USER_INSIGHT:
            raise TimeoutError
        return {
            "status": "success",
            "compressed_summary": "summary",
            "recent_messages": [],
        }

    rpc_client.send_request = AsyncMock(side_effect=send_request)
    config = MagicMock()
    config.short_timeout = 10.0
    config.request_topics = {"memory": "memory"}
    service = ChatService(rpc_client, MagicMock(), config)

    result = asyncio.run(
        service._prepare_context(ChatRequest(message="hello", chat_id="chat-1"))
    )

    assert result == (
        "",
        "[Earlier conversation summary]: summary",
        "[Earlier conversation summary]: summary",
    )
    assert rpc_client.send_request.await_count == 2


def test_prepare_context_cancellation_cleans_up_both_branches():
    service = object.__new__(ChatService)
    both_started = asyncio.Event()
    history_finished = asyncio.Event()
    started = set()

    async def wait_for_cancellation(branch):
        started.add(branch)
        if len(started) == 2:
            both_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            if branch == "history":
                history_finished.set()

    async def fetch_insight():
        await wait_for_cancellation("insight")
        return ""

    async def fetch_history(_request):
        await wait_for_cancellation("history")
        return "", None

    service._fetch_user_insight = fetch_insight
    service._fetch_history = fetch_history

    async def exercise():
        task = asyncio.create_task(
            service._prepare_context(ChatRequest(message="hello", chat_id="chat-1"))
        )
        await asyncio.wait_for(both_started.wait(), timeout=0.1)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await asyncio.wait_for(history_finished.wait(), timeout=0.1)
        assert task.cancelled()

    asyncio.run(exercise())
