"""Tests for memory service endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock

from app.main import app, runtime
from app.rest.dependencies import service_container
from app.services.chat_service import ChatService
from app.services.message_service import MessageService
from shared.logging import ServiceLogger
from shared.auth import AuthIdentity, sign_auth_ticket


@pytest.fixture
def client(monkeypatch):
    """Create test client."""
    secret = "memory-test-internal-auth-secret-32-bytes"
    identity = AuthIdentity(
        tenant_id="tenant-test",
        user_id="memory-test-service",
        role="service",
    )
    ticket = sign_auth_ticket(identity, secret=secret, audience="internal")

    async def no_op_lifecycle():
        return None

    monkeypatch.setenv("INTERNAL_AUTH_SECRET", secret)
    monkeypatch.setattr(runtime, "start", no_op_lifecycle)
    monkeypatch.setattr(runtime, "shutdown", no_op_lifecycle)
    app.dependency_overrides = {}
    with TestClient(app, headers={"X-Internal-Auth": ticket}) as test_client:
        yield test_client
    app.dependency_overrides = {}


@pytest.fixture
def mock_logger():
    """Create mock logger."""
    return Mock(spec=ServiceLogger)


@pytest.fixture
def mock_chat_service(mock_logger):
    """Create mock chat service."""
    service = Mock(spec=ChatService)
    service.create_chat.return_value = {
        "id": "test-chat-1",
        "title": "Test Chat",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00"
    }
    service.get_all_chats.return_value = [
        {
            "id": "test-chat-1",
            "title": "Test Chat",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00"
        }
    ]
    service.get_chat.return_value = {
        "id": "test-chat-1",
        "title": "Test Chat",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00"
    }
    return service


@pytest.fixture
def mock_message_service():
    """Create mock message service."""
    service = Mock(spec=MessageService)
    service.add_message.return_value = {
        "id": "msg-1",
        "chat_id": "test-chat-1",
        "sender": "User",
        "message": "hello",
        "timestamp": "2024-01-01T00:00:00",
    }
    service.get_messages.return_value = [
        {
            "id": "msg-1",
            "chat_id": "test-chat-1",
            "sender": "User",
            "message": "hello",
            "timestamp": "2024-01-01T00:00:00",
        }
    ]
    return service


@pytest.fixture
def override_chat_service(mock_chat_service):
    """Override the chat-service dependency."""
    app.dependency_overrides[service_container.get_chat_service] = lambda: mock_chat_service
    return mock_chat_service


@pytest.fixture
def override_message_service(mock_message_service):
    """Override the message-service dependency."""
    app.dependency_overrides[service_container.get_message_service] = lambda: mock_message_service
    return mock_message_service


def test_create_chat(client, override_chat_service, mock_logger):
    """Test creating a chat."""
    response = client.post(
        "/api/v1/chats",
        json={"chat_id": "test-chat-1", "title": "Test Chat"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "test-chat-1"
    assert data["title"] == "Test Chat"


def test_get_chats(client, override_chat_service):
    """Test getting all chats."""
    response = client.get("/api/v1/chats")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["chats"]) == 1


def test_get_chat(client, override_chat_service):
    """Test getting a specific chat."""
    response = client.get("/api/v1/chats/test-chat-1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-chat-1"


def test_delete_chat(client, override_chat_service, override_message_service):
    """Test deleting a chat and its messages."""
    response = client.delete("/api/v1/chats/test-chat-1")

    assert response.status_code == 204
    override_message_service.delete_messages_by_chat.assert_called_once_with("test-chat-1")
    override_chat_service.delete_chat.assert_called_once_with("test-chat-1")


def test_add_message(client, override_message_service):
    """Test adding a message."""
    response = client.post(
        "/api/v1/messages",
        json={
            "chat_id": "test-chat-1",
            "message_id": "msg-1",
            "sender": "User",
            "message": "hello",
            "metadata": {"turnId": "turn-1"},
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == "msg-1"
    override_message_service.add_message.assert_called_once_with(
        "msg-1", "test-chat-1", "User", "hello", {"turnId": "turn-1"}
    )


def test_get_messages(client, override_message_service):
    """Test getting messages for a chat."""
    response = client.get("/api/v1/chats/test-chat-1/messages")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["messages"]) == 1


def test_health(client, override_chat_service):
    """Test the REST health endpoint."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["chats_count"] == 1
    assert data["db_type"] == "mongodb"
