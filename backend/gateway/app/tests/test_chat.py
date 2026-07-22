"""Tests for chat endpoints."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
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
