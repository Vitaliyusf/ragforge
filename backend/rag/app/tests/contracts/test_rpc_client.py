"""Focused tests for authenticated RAG RPC reply handling."""

import asyncio
import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.messaging.rpc_client import RabbitMQRPCClient
from app.services.conversation_messages import DownstreamRPCError, extract_reply_payload
from shared.auth import AuthError, AuthIdentity, attach_internal_auth_context
from shared.context import bound_context


TEST_SECRET = "rag-rpc-test-secret-with-at-least-32-bytes"
TEST_IDENTITY = AuthIdentity(tenant_id="internal", user_id="embedding-service", role="service")


class FakeConfig:
    rabbitmq_url = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange = "ragapp.requests"
    service_name = "rag"
    stream_drain_timeout_seconds = 0.1


class FakeQueueIterator:
    def __init__(self, messages: list[Any]) -> None:
        self.messages = iter(messages)

    async def __aenter__(self) -> "FakeQueueIterator":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    def __aiter__(self) -> "FakeQueueIterator":
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self.messages)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeQueue:
    def __init__(self, message: Any) -> None:
        self.message = message

    def iterator(self) -> FakeQueueIterator:
        return FakeQueueIterator([self.message])


def signed_reply(payload: Dict[str, Any]) -> Dict[str, Any]:
    with bound_context(**TEST_IDENTITY.to_dict()):
        return attach_internal_auth_context(dict(payload), secret=TEST_SECRET)


def incoming_message(payload: Dict[str, Any]) -> MagicMock:
    message = MagicMock()
    message.body = json.dumps(payload).encode()
    message.correlation_id = "corr-auth"
    message.process = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))
    return message


@pytest.fixture(autouse=True)
def require_signed_replies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", TEST_SECRET)


@pytest.mark.asyncio
async def test_structured_auth_error_is_received_promptly_and_not_as_timeout() -> None:
    client = RabbitMQRPCClient(FakeConfig())  # type: ignore[arg-type]
    reply = signed_reply({
        "message_type": "reply",
        "success": False,
        "correlation_id": "corr-auth",
        "error": {
            "code": "internal_auth_expired",
            "message": "Internal authentication context expired",
        },
    })

    received = await asyncio.wait_for(
        client._wait_for_reply(FakeQueue(incoming_message(reply)), "corr-auth"),  # type: ignore[arg-type]
        timeout=0.1,
    )

    with pytest.raises(DownstreamRPCError) as exc_info:
        extract_reply_payload(received)
    assert exc_info.value.code == "internal_auth_expired"


@pytest.mark.asyncio
async def test_successful_signed_reply_verification_is_unchanged() -> None:
    client = RabbitMQRPCClient(FakeConfig())  # type: ignore[arg-type]
    reply = signed_reply({
        "message_type": "reply",
        "success": True,
        "correlation_id": "corr-auth",
        "payload": {"embedding": [0.1, 0.2]},
    })

    received = await client._wait_for_reply(  # type: ignore[arg-type]
        FakeQueue(incoming_message(reply)),
        "corr-auth",
    )

    assert extract_reply_payload(received)["embedding"] == [0.1, 0.2]


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [{"success": True}, {"success": True, "auth_context": "invalid"}])
async def test_unsigned_or_invalid_reply_is_still_rejected(reply: Dict[str, Any]) -> None:
    client = RabbitMQRPCClient(FakeConfig())  # type: ignore[arg-type]

    with pytest.raises(AuthError):
        await client._wait_for_reply(  # type: ignore[arg-type]
            FakeQueue(incoming_message(reply)),
            "corr-auth",
        )
