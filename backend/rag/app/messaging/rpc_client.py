"""Native async RabbitMQ RPC client for RAG downstream calls.

RAG uses one exclusive reply queue per request. Answer generation also gets a
temporary, uniquely-bound stream queue so LLM token events stay on RabbitMQ
without reintroducing a shared reply topic or correlation matcher.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import uuid4

import aio_pika
import aio_pika.abc

from app.core.config import RAGConfig
from shared.auth import attach_internal_auth_context, verify_internal_ticket_from_envelope


StreamCallback = Callable[[Dict[str, Any]], Awaitable[None]]


class RabbitMQRPCClient:
    """Publish typed envelopes and await correlated RabbitMQ replies."""

    def __init__(self, config: RAGConfig) -> None:
        self._url = config.rabbitmq_url
        self._exchange_name = config.rabbitmq_exchange
        self._stream_drain_timeout = config.stream_drain_timeout_seconds
        self._connection: Optional[aio_pika.abc.AbstractRobustConnection] = None

    async def connect(self) -> None:
        """Establish the robust connection used by request-scoped channels."""
        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(self._url)

    async def close(self) -> None:
        """Close the shared robust connection."""
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None

    def is_connected(self) -> bool:
        """Return whether downstream RPC publishing can currently proceed."""
        return self._connection is not None and not self._connection.is_closed

    async def request(
        self,
        routing_key: str,
        envelope: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Send one RPC request and return the complete reply envelope."""
        return await self._request(
            routing_key=routing_key,
            envelope=envelope,
            timeout=timeout,
            stream_callback=None,
        )

    async def request_stream(
        self,
        routing_key: str,
        envelope: Dict[str, Any],
        timeout: float,
        stream_callback: StreamCallback,
    ) -> Dict[str, Any]:
        """Send an RPC request and consume its ordered stream events."""
        return await self._request(
            routing_key=routing_key,
            envelope=envelope,
            timeout=timeout,
            stream_callback=stream_callback,
        )

    async def publish(self, routing_key: str, envelope: Dict[str, Any]) -> None:
        """Publish a fire-and-forget command or domain event."""
        connection = self._require_connection()
        async with connection.channel() as channel:
            exchange = await channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(attach_internal_auth_context(envelope)).encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=routing_key,
            )

    async def _request(
        self,
        *,
        routing_key: str,
        envelope: Dict[str, Any],
        timeout: float,
        stream_callback: Optional[StreamCallback],
    ) -> Dict[str, Any]:
        connection = self._require_connection()
        stream_task: Optional[asyncio.Task[None]] = None

        async with connection.channel() as channel:
            exchange = await channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            reply_queue = await channel.declare_queue(exclusive=True, auto_delete=True)

            body = dict(envelope)
            correlation_id = str(body.get("correlation_id") or uuid4())
            body["correlation_id"] = correlation_id
            body["reply_to"] = reply_queue.name

            if stream_callback is not None:
                stream_routing_key = f"rag.stream.{uuid4()}"
                stream_queue = await channel.declare_queue(exclusive=True, auto_delete=True)
                await stream_queue.bind(exchange, routing_key=stream_routing_key)
                body["stream_to"] = stream_routing_key
                stream_task = asyncio.create_task(
                    self._consume_stream(stream_queue, stream_callback)
                )

            attach_internal_auth_context(body)

            reply_task = asyncio.create_task(self._wait_for_reply(reply_queue, correlation_id))
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(body).encode("utf-8"),
                    correlation_id=correlation_id,
                    reply_to=reply_queue.name,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=routing_key,
            )

            try:
                try:
                    async with asyncio.timeout(timeout):
                        reply = await reply_task
                except TimeoutError as exc:
                    raise TimeoutError(
                        f"RabbitMQ RPC timeout waiting for '{routing_key}' after {timeout:.1f}s"
                    ) from exc

                if stream_task is not None:
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(stream_task),
                            timeout=self._stream_drain_timeout,
                        )
                    except asyncio.TimeoutError:
                        # The final reply is authoritative. Providers that do not
                        # emit stream events must not delay the completed answer.
                        stream_task.cancel()
                        await asyncio.gather(stream_task, return_exceptions=True)
                return reply
            finally:
                if not reply_task.done():
                    reply_task.cancel()
                if stream_task is not None and not stream_task.done():
                    stream_task.cancel()
                await asyncio.gather(
                    *[task for task in (reply_task, stream_task) if task is not None],
                    return_exceptions=True,
                )

    async def _wait_for_reply(
        self,
        queue: aio_pika.abc.AbstractQueue,
        correlation_id: str,
    ) -> Dict[str, Any]:
        async with queue.iterator() as iterator:
            async for message in iterator:
                async with message.process():
                    if message.correlation_id and message.correlation_id != correlation_id:
                        continue
                    payload = json.loads(message.body)
                    if not isinstance(payload, dict):
                        raise RuntimeError("RabbitMQ RPC reply must be a JSON object")
                    verify_internal_ticket_from_envelope(payload, required=True)
                    return payload
        raise RuntimeError("RabbitMQ reply queue closed before a response arrived")

    async def _consume_stream(
        self,
        queue: aio_pika.abc.AbstractQueue,
        callback: StreamCallback,
    ) -> None:
        async with queue.iterator() as iterator:
            async for message in iterator:
                async with message.process():
                    event = json.loads(message.body)
                    if not isinstance(event, dict):
                        continue
                    verify_internal_ticket_from_envelope(event, required=True)
                    await callback(event)
                    payload = event.get("payload")
                    event_type = payload.get("event_type") if isinstance(payload, dict) else None
                    if event_type in {"llm.done", "llm.error"}:
                        return

    def _require_connection(self) -> aio_pika.abc.AbstractRobustConnection:
        if self._connection is None or self._connection.is_closed:
            raise RuntimeError("RabbitMQ RPC client is not connected")
        return self._connection
