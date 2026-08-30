"""Unit tests for shared RabbitMQ base classes."""
import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.auth import (
    AuthError,
    AuthIdentity,
    attach_internal_auth_context,
    internal_envelope_digest,
    sign_auth_ticket,
    verify_internal_ticket_from_envelope,
)
from shared.context import bound_context
from shared.bounded_executor import ExecutorOverloaded
from shared.rabbitmq_base import BaseRabbitMQConsumer, BaseRabbitMQProducer


TEST_SECRET = "rabbitmq-test-secret-with-at-least-32-bytes"
TEST_IDENTITY = AuthIdentity(
    tenant_id="tenant-a",
    user_id="user-a",
    role="user",
    admin_id="admin-a",
)


@pytest.fixture(autouse=True)
def require_signed_internal_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", TEST_SECRET)


def signed_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    with bound_context(**TEST_IDENTITY.to_dict()):
        return attach_internal_auth_context(dict(payload), secret=TEST_SECRET)


def expired_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(payload)
    body["auth_context"] = sign_auth_ticket(
        TEST_IDENTITY,
        secret=TEST_SECRET,
        audience="internal",
        purpose="request",
        issuer="ragapp-internal",
        ttl_seconds=1,
        now=1,
        extra_claims={"payload_sha256": internal_envelope_digest(body)},
    )
    return body


def mock_incoming_message(
    body: Dict[str, Any],
    *,
    reply_to: str = "amq.rabbitmq.reply.auth",
    correlation_id: str = "corr-auth",
) -> MagicMock:
    message = MagicMock()
    message.body = json.dumps(body).encode()
    message.reply_to = reply_to
    message.correlation_id = correlation_id
    message.process = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))
    return message


class FakeConfig:
    rabbitmq_url = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange = "ragapp.requests"
    rabbitmq_queue = "test_queue"
    rabbitmq_prefetch_count = 1


@pytest.mark.asyncio
async def test_consumer_calls_handler_with_body_reply_to_correlation_id() -> None:
    config = FakeConfig()
    consumer = BaseRabbitMQConsumer(config)

    received = {}

    async def handler(body: Any, reply_to: Any, correlation_id: Any) -> Any:
        received["body"] = body
        received["reply_to"] = reply_to
        received["correlation_id"] = correlation_id
        return {"success": True}

    mock_message = MagicMock()
    mock_message.body = json.dumps(signed_message({"action": "test"})).encode()
    mock_message.reply_to = "amq.rabbitmq.reply.1234"
    mock_message.correlation_id = "corr-abc"
    mock_message.process = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))

    mock_channel = AsyncMock()
    mock_channel.default_exchange = AsyncMock()
    consumer._channel = mock_channel

    await consumer._dispatch(mock_message, handler)

    assert received["body"]["action"] == "test"
    assert received["body"]["auth_context"]
    assert received["reply_to"] == "amq.rabbitmq.reply.1234"
    assert received["correlation_id"] == "corr-abc"
    mock_channel.default_exchange.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_does_not_publish_when_handler_returns_none() -> None:
    config = FakeConfig()
    consumer = BaseRabbitMQConsumer(config)

    async def handler(body: Any, reply_to: Any, correlation_id: Any) -> Any:
        return None

    mock_message = MagicMock()
    mock_message.body = json.dumps(signed_message({"action": "fire_and_forget"})).encode()
    mock_message.reply_to = ""
    mock_message.correlation_id = ""
    mock_message.process = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    ))

    mock_channel = AsyncMock()
    consumer._channel = mock_channel

    await consumer._dispatch(mock_message, handler)

    mock_channel.default_exchange.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_producer_reply_publishes_to_default_exchange() -> None:
    config = FakeConfig()
    producer = BaseRabbitMQProducer(config)

    mock_channel = AsyncMock()
    producer._channel = mock_channel

    with bound_context(**TEST_IDENTITY.to_dict()):
        await producer.reply("reply-queue-xyz", "corr-123", {"result": "ok"})

    mock_channel.default_exchange.publish.assert_awaited_once()
    call_args = mock_channel.default_exchange.publish.call_args
    assert call_args.kwargs["routing_key"] == "reply-queue-xyz"
    published_body = json.loads(call_args.args[0].body)
    assert published_body["result"] == "ok"
    assert published_body["auth_context"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        (expired_message({"action": "test"}), "internal_auth_expired"),
        ({"action": "test"}, "internal_auth_required"),
    ],
)
async def test_rpc_auth_failure_returns_safe_signed_reply(
    body: Dict[str, Any],
    expected_code: str,
) -> None:
    consumer = BaseRabbitMQConsumer(FakeConfig())
    mock_channel = AsyncMock()
    mock_channel.default_exchange = AsyncMock()
    consumer._channel = mock_channel
    handler = AsyncMock()

    await consumer._dispatch(mock_incoming_message(body), handler)

    handler.assert_not_awaited()
    published = mock_channel.default_exchange.publish.await_args
    assert published.kwargs["routing_key"] == "amq.rabbitmq.reply.auth"
    reply_message = published.args[0]
    assert reply_message.correlation_id == "corr-auth"
    reply = json.loads(reply_message.body)
    assert reply["success"] is False
    assert reply["error"]["code"] == expected_code
    assert "ticket" not in json.dumps(reply).lower()
    identity = verify_internal_ticket_from_envelope(reply, required=True)
    assert identity is not None
    assert identity.is_service


@pytest.mark.asyncio
async def test_invalid_signature_rpc_returns_auth_invalid_reply() -> None:
    body = signed_message({"action": "test"})
    encoded, signature = body["auth_context"].split(".", 1)
    # Corrupt the first character of the signature, never the last. A 32-byte
    # HMAC encodes to 43 unpadded base64url characters, and the final one only
    # carries four significant bits, so four different characters decode to the
    # same signature bytes. Substituting the last character therefore leaves the
    # ticket valid whenever the substitute lands in that group, which made this
    # test pass or fail on the randomness of the ticket's `jti`.
    replacement = "A" if signature[0] != "A" else "B"
    body["auth_context"] = f"{encoded}.{replacement}{signature[1:]}"
    consumer = BaseRabbitMQConsumer(FakeConfig())
    mock_channel = AsyncMock()
    mock_channel.default_exchange = AsyncMock()
    consumer._channel = mock_channel
    handler = AsyncMock()

    await consumer._dispatch(mock_incoming_message(body), handler)

    handler.assert_not_awaited()
    reply = json.loads(mock_channel.default_exchange.publish.await_args.args[0].body)
    assert reply["error"] == {
        "code": "internal_auth_invalid",
        "message": "Internal authentication context invalid",
    }
    verify_internal_ticket_from_envelope(reply, required=True)


@pytest.mark.asyncio
async def test_fire_and_forget_auth_failure_does_not_invent_reply() -> None:
    consumer = BaseRabbitMQConsumer(FakeConfig())
    mock_channel = AsyncMock()
    mock_channel.default_exchange = AsyncMock()
    consumer._channel = mock_channel

    with pytest.raises(AuthError):
        await consumer._dispatch(
            mock_incoming_message(
                expired_message({"action": "test"}),
                reply_to="",
                correlation_id="",
            ),
            AsyncMock(),
        )

    mock_channel.default_exchange.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_unexpected_handler_failure_still_raises_without_reply() -> None:
    consumer = BaseRabbitMQConsumer(FakeConfig())
    mock_channel = AsyncMock()
    mock_channel.default_exchange = AsyncMock()
    consumer._channel = mock_channel
    handler = AsyncMock(side_effect=RuntimeError("handler failed"))

    with pytest.raises(RuntimeError, match="handler failed"):
        await consumer._dispatch(mock_incoming_message(signed_message({"action": "test"})), handler)

    mock_channel.default_exchange.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_executor_overload_publishes_typed_retryable_reply() -> None:
    consumer = BaseRabbitMQConsumer(FakeConfig())
    mock_channel = AsyncMock()
    mock_channel.default_exchange = AsyncMock()
    consumer._channel = mock_channel
    handler = AsyncMock(side_effect=ExecutorOverloaded("files", "rpc"))

    await consumer._dispatch(
        mock_incoming_message(signed_message({"action": "test"})),
        handler,
    )

    mock_channel.default_exchange.publish.assert_awaited_once()
    call = mock_channel.default_exchange.publish.call_args
    published = json.loads(call.args[0].body)
    assert call.kwargs["routing_key"] == "amq.rabbitmq.reply.auth"
    assert call.args[0].correlation_id == "corr-auth"
    assert published["correlation_id"] == "corr-auth"
    assert published["success"] is False
    assert published["error"] == {
        "code": "service_overloaded",
        "message": "Service is busy; retry later",
        "retryable": True,
    }
    assert published["auth_context"]
