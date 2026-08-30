"""Deterministic concurrency contract for the shared RabbitMQ RPC transport."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from shared.auth import AuthIdentity, ROLE_USER, attach_internal_auth_context
from shared.context import bound_context
from shared.rabbitmq_rpc import MultiplexedRabbitMQRPCClient


SECRET = "multiplexed-rpc-test-secret-with-at-least-32-bytes"
IDENTITY = AuthIdentity(
    tenant_id="tenant-a",
    user_id="user-a",
    role=ROLE_USER,
)


@asynccontextmanager
async def _processed() -> Any:
    yield


class FakeMessage:
    def __init__(self, payload: dict[str, Any], correlation_id: str) -> None:
        self.body = json.dumps(payload).encode("utf-8")
        self.correlation_id = correlation_id

    def process(self) -> Any:
        return _processed()


class FakeQueue:
    name = "amq.gen.shared-replies"

    def __init__(self) -> None:
        self.callback: Any = None
        self.bind_count = 0
        self.consume_count = 0

    async def bind(self, _exchange: Any, *, routing_key: str) -> None:
        self.bind_count += 1
        self.stream_routing_key = routing_key

    async def consume(self, callback: Any) -> str:
        self.consume_count += 1
        self.callback = callback
        return "consumer-1"

    async def cancel(self, _consumer_tag: str) -> None:
        return None

    async def deliver(self, payload: dict[str, Any], correlation_id: str) -> None:
        assert self.callback is not None
        await self.callback(FakeMessage(payload, correlation_id))


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[str, Any]] = []

    async def publish(self, message: Any, *, routing_key: str) -> None:
        self.published.append((routing_key, message))


class FakeChannel:
    def __init__(self) -> None:
        self.is_closed = False
        self.exchange = FakeExchange()
        self.queue = FakeQueue()
        self.exchange_declarations = 0
        self.queue_declarations = 0

    async def declare_exchange(self, *_args: Any, **_kwargs: Any) -> FakeExchange:
        self.exchange_declarations += 1
        return self.exchange

    async def declare_queue(self, **_kwargs: Any) -> FakeQueue:
        self.queue_declarations += 1
        return self.queue

    async def close(self) -> None:
        self.is_closed = True


class FakeConnection:
    def __init__(self) -> None:
        self.is_closed = False
        self.channel_value = FakeChannel()
        self.channel_count = 0

    async def channel(self) -> FakeChannel:
        self.channel_count += 1
        return self.channel_value

    async def close(self) -> None:
        self.is_closed = True


def _signed(payload: dict[str, Any]) -> dict[str, Any]:
    with bound_context(**IDENTITY.to_dict()):
        return attach_internal_auth_context(dict(payload), secret=SECRET)


def _client() -> MultiplexedRabbitMQRPCClient:
    return MultiplexedRabbitMQRPCClient(
        "amqp://unused",
        "requests",
        "test",
        max_inflight=128,
        stream_drain_timeout=0.2,
    )


def _published_body(exchange: FakeExchange, index: int) -> dict[str, Any]:
    payload = json.loads(exchange.published[index][1].body)
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


async def _wait_for_publishes(exchange: FakeExchange, count: int) -> None:
    async with asyncio.timeout(1):
        while len(exchange.published) < count:
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_128_out_of_order_replies_share_one_transport_and_correlate(monkeypatch: Any) -> None:
    connection = FakeConnection()
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr("shared.rabbitmq_rpc.aio_pika.connect_robust", connect)
    client = _client()
    await client.connect()

    calls = [
        asyncio.create_task(
            client.request(
                "embedding",
                {"correlation_id": f"corr-{index}", "payload": {"index": index}},
                timeout=1,
                auth_kwargs={"secret": SECRET, "identity": IDENTITY},
            )
        )
        for index in range(128)
    ]
    exchange = connection.channel_value.exchange
    queue = connection.channel_value.queue
    await _wait_for_publishes(exchange, 128)
    published = {
        int(_published_body(exchange, index)["payload"]["index"]):
        exchange.published[index][1].correlation_id
        for index in range(128)
    }
    for index in reversed(range(128)):
        correlation_id = published[index]
        await queue.deliver(
            _signed({
                "message_type": "reply",
                "correlation_id": correlation_id,
                "success": True,
                "payload": {"index": index},
            }),
            correlation_id,
        )

    replies = await asyncio.gather(*calls)
    assert [reply["payload"]["index"] for reply in replies] == list(range(128))
    assert client.waiter_count == 0
    assert connect.await_count == 1
    assert connection.channel_count == 1
    assert connection.channel_value.exchange_declarations == 1
    assert connection.channel_value.queue_declarations == 1
    await client.close()


@pytest.mark.asyncio
async def test_timeout_cancellation_and_late_replies_leave_no_waiters(monkeypatch: Any) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(
        "shared.rabbitmq_rpc.aio_pika.connect_robust",
        AsyncMock(return_value=connection),
    )
    client = _client()
    await client.connect()
    auth = {"secret": SECRET, "identity": IDENTITY}

    with pytest.raises(TimeoutError):
        await client.request(
            "embedding",
            {"correlation_id": "timed-out"},
            timeout=0.01,
            auth_kwargs=auth,
        )
    assert client.waiter_count == 0
    timed_out_id = connection.channel_value.exchange.published[0][1].correlation_id
    await connection.channel_value.queue.deliver(
        _signed({"message_type": "reply", "correlation_id": timed_out_id}),
        timed_out_id,
    )

    cancelled = asyncio.create_task(
        client.request(
            "embedding",
            {"correlation_id": "cancelled"},
            timeout=1,
            auth_kwargs=auth,
        )
    )
    await _wait_for_publishes(connection.channel_value.exchange, 2)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert client.waiter_count == 0
    cancelled_id = connection.channel_value.exchange.published[1][1].correlation_id
    await connection.channel_value.queue.deliver(
        _signed({"message_type": "reply", "correlation_id": cancelled_id}),
        cancelled_id,
    )
    assert client.waiter_count == 0
    await client.close()


@pytest.mark.asyncio
async def test_inflight_limit_bounds_published_requests_and_waiter_registry(monkeypatch: Any) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(
        "shared.rabbitmq_rpc.aio_pika.connect_robust",
        AsyncMock(return_value=connection),
    )
    client = MultiplexedRabbitMQRPCClient(
        "amqp://unused",
        "requests",
        "test",
        max_inflight=2,
    )
    await client.connect()
    auth = {"secret": SECRET, "identity": IDENTITY}
    calls = [
        asyncio.create_task(
            client.request(
                "embedding",
                {"correlation_id": "shared-parent", "payload": {"index": index}},
                timeout=1,
                auth_kwargs=auth,
            )
        )
        for index in range(3)
    ]
    exchange = connection.channel_value.exchange
    queue = connection.channel_value.queue
    await _wait_for_publishes(exchange, 2)
    await asyncio.sleep(0)
    assert len(exchange.published) == 2
    assert client.waiter_count == 2

    first_id = exchange.published[0][1].correlation_id
    await queue.deliver(_signed({"message_type": "reply", "correlation_id": first_id}), first_id)
    await _wait_for_publishes(exchange, 3)
    for published_index in (1, 2):
        correlation_id = exchange.published[published_index][1].correlation_id
        await queue.deliver(
            _signed({"message_type": "reply", "correlation_id": correlation_id}),
            correlation_id,
        )
    await asyncio.gather(*calls)
    assert client.waiter_count == 0
    await client.close()


@pytest.mark.asyncio
async def test_hard_close_recreates_resources_and_shutdown_fails_waiters(monkeypatch: Any) -> None:
    first = FakeConnection()
    second = FakeConnection()
    connect = AsyncMock(side_effect=[first, second])
    monkeypatch.setattr("shared.rabbitmq_rpc.aio_pika.connect_robust", connect)
    client = _client()
    await client.connect()
    first.is_closed = True

    recovered = asyncio.create_task(
        client.request(
            "memory",
            {"correlation_id": "after-reconnect"},
            timeout=1,
            auth_kwargs={"secret": SECRET, "identity": IDENTITY},
        )
    )
    await _wait_for_publishes(second.channel_value.exchange, 1)
    recovered_id = second.channel_value.exchange.published[0][1].correlation_id
    await second.channel_value.queue.deliver(
        _signed({
            "message_type": "reply",
            "correlation_id": recovered_id,
            "success": True,
        }),
        recovered_id,
    )
    assert (await recovered)["success"] is True
    assert connect.await_count == 2

    outstanding = asyncio.create_task(
        client.request(
            "memory",
            {"correlation_id": "during-shutdown"},
            timeout=10,
            auth_kwargs={"secret": SECRET, "identity": IDENTITY},
        )
    )
    await _wait_for_publishes(second.channel_value.exchange, 2)
    await client.close()
    with pytest.raises(RuntimeError, match="client closed"):
        await outstanding
    assert client.waiter_count == 0


@pytest.mark.asyncio
async def test_streams_are_ordered_isolated_and_drained_after_final_reply(monkeypatch: Any) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(
        "shared.rabbitmq_rpc.aio_pika.connect_robust",
        AsyncMock(return_value=connection),
    )
    client = _client()
    await client.connect()
    seen: dict[str, list[str]] = {"a": [], "b": []}

    def callback_for(name: str) -> Any:
        async def callback(event: dict[str, Any]) -> None:
            seen[name].append(event["payload"]["value"])

        return callback

    calls = {
        name: asyncio.create_task(
            client.request(
                "llm_agent",
                {"correlation_id": "shared-parent", "payload": {"name": name}},
                timeout=1,
                auth_kwargs={"secret": SECRET, "identity": IDENTITY},
                stream_callback=callback_for(name),
            )
        )
        for name in ("a", "b")
    }
    await _wait_for_publishes(connection.channel_value.exchange, 2)
    queue = connection.channel_value.queue
    stream_ids = {
        _published_body(connection.channel_value.exchange, index)["payload"]["name"]:
        connection.channel_value.exchange.published[index][1].correlation_id
        for index in range(2)
    }
    for name, value, event_type in (
        ("a", "a1", "llm.token"),
        ("b", "b1", "llm.token"),
        ("a", "a2", "llm.done"),
        ("b", "b2", "llm.done"),
    ):
        correlation_id = stream_ids[name]
        await queue.deliver(
            _signed({
                "message_type": "stream_event",
                "correlation_id": correlation_id,
                "payload": {"event_type": event_type, "value": value},
            }),
            correlation_id,
        )
    for name in ("b", "a"):
        correlation_id = stream_ids[name]
        await queue.deliver(
            _signed({
                "message_type": "reply",
                "correlation_id": correlation_id,
                "success": True,
            }),
            correlation_id,
        )

    await asyncio.gather(*calls.values())
    assert seen == {"a": ["a1", "a2"], "b": ["b1", "b2"]}
    assert client.waiter_count == 0
    await client.close()
