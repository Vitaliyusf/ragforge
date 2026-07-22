"""Unit tests for shared RabbitMQ base classes."""
import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.auth import AuthIdentity, attach_internal_auth_context
from shared.context import bound_context
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
