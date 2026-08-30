"""Native async RabbitMQ RPC client for RAG downstream calls."""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, Optional
import aio_pika
import aio_pika.abc

from app.core.config import RAGConfig
from shared.auth import verify_internal_ticket_from_envelope
from shared.rabbitmq_rpc import MultiplexedRabbitMQRPCClient


StreamCallback = Callable[[Dict[str, Any]], Awaitable[None]]


class RabbitMQRPCClient:
    """Publish typed envelopes and await correlated RabbitMQ replies."""

    def __init__(self, config: RAGConfig) -> None:
        self._url = config.rabbitmq_url
        self._exchange_name = config.rabbitmq_exchange
        self._stream_drain_timeout = config.stream_drain_timeout_seconds
        self._transport = MultiplexedRabbitMQRPCClient(
            self._url,
            self._exchange_name,
            config.service_name,
            max_inflight=getattr(config, "rabbitmq_rpc_max_inflight", 64),
            stream_drain_timeout=self._stream_drain_timeout,
            # ConversationBackendClient is the existing CONC-00 metrics owner.
            record_metrics=False,
        )

    async def connect(self) -> None:
        """Establish the reusable robust RPC transport."""
        await self._transport.connect()

    async def close(self) -> None:
        """Close the shared robust connection."""
        await self._transport.close()

    def is_connected(self) -> bool:
        """Return whether downstream RPC publishing can currently proceed."""
        return self._transport.is_connected()

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
        await self._transport.publish(routing_key, envelope)

    async def _request(
        self,
        *,
        routing_key: str,
        envelope: Dict[str, Any],
        timeout: float,
        stream_callback: Optional[StreamCallback],
    ) -> Dict[str, Any]:
        return await self._transport.request(
            routing_key,
            envelope,
            timeout=timeout,
            stream_callback=stream_callback,
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
