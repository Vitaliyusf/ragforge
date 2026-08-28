"""Native async RabbitMQ RPC client — replaces GatewayKafkaRequestClient."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Dict, Optional

import aio_pika
import aio_pika.abc

from app.core.config import GatewayConfig
from app.core.correlation import ensure_correlation_ids
from app.core.errors import GatewayError, NotFoundError, ServiceUnavailableError, ValidationError
from shared.logging import ServiceLogger
from app.core.request_context import get_request_context
from app.schemas.common import MessageEnvelope, ReplyEnvelope, MessageType
from shared.auth import attach_internal_auth_context, identity_from_context, verify_internal_ticket_from_envelope


class GatewayRPCClient:
    """Publish a request envelope and await a reply on an exclusive auto-delete queue.

    Each call to ``request()`` creates its own reply queue which self-destructs
    after the response arrives. No shared reply topic. No request matcher.
    No background thread.
    """

    def __init__(
        self,
        config: GatewayConfig,
        logger: ServiceLogger,
    ) -> None:
        self._url: str = config.rabbitmq_url
        self._exchange_name: str = config.rabbitmq_exchange
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self.logger = logger
        self.config = config

    async def connect(self) -> None:
        """Establish the RabbitMQ connection."""
        self._connection = await aio_pika.connect_robust(self._url)

    async def close(self) -> None:
        """Close the RabbitMQ connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    def is_connected(self) -> bool:
        """Return whether the robust RabbitMQ connection is currently usable."""
        return self._connection is not None and not self._connection.is_closed

    async def request(
        self,
        routing_key: str,
        payload: Dict[str, Any],
        timeout: float = 30.0,
        target_service: Optional[str] = None,
        message_type: Optional[MessageType] = None,
    ) -> Dict[str, Any]:
        """Publish a typed request envelope and wait for the reply."""
        action = payload.get("action", "request")
        business_payload = {k: v for k, v in payload.items() if k != "action"}
        target_service = target_service or routing_key
        message_type = message_type or self._infer_message_type(action)

        context = get_request_context()
        request_id, trace_id = ensure_correlation_ids(
            context.get("request_id"),
            context.get("trace_id"),
        )
        correlation_id = str(uuid.uuid4())
        identity = identity_from_context()
        if self._connection is None:
            raise RuntimeError("RabbitMQ connection is not established")
        async with self._connection.channel() as channel:
            exchange = await channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            reply_queue = await channel.declare_queue(exclusive=True, auto_delete=True)

            envelope = MessageEnvelope(
                message_id=str(uuid.uuid4()),
                message_type=message_type,
                action=action,
                source_service=self.config.service_name,
                target_service=target_service,
                request_id=request_id,
                trace_id=trace_id,
                correlation_id=correlation_id,
                timestamp=int(time.time() * 1000),
                auth_context="pending",
                payload=business_payload,
            )
            envelope_dict = envelope.model_dump(mode="python", exclude_none=True)
            envelope_dict["reply_to"] = reply_queue.name
            attach_internal_auth_context(
                envelope_dict,
                ttl_seconds=self.config.internal_auth_ticket_ttl_seconds,
                identity=identity,
                secret=self.config.internal_auth_secret,
            )

            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(envelope_dict).encode(),
                    correlation_id=correlation_id,
                    reply_to=reply_queue.name,
                    content_type="application/json",
                ),
                routing_key=routing_key,
            )

            self.logger.log(
                "rpc_client:request",
                "RPC request published",
                {
                    "routing_key": routing_key,
                    "action": action,
                    "target_service": target_service,
                    "correlation_id": correlation_id,
                },
            )

            async with asyncio.timeout(timeout):
                async for message in reply_queue.iterator():
                    async with message.process():
                        raw_reply = json.loads(message.body)
                        if not isinstance(raw_reply, dict):
                            raise GatewayError("RPC reply must be a JSON object")
                        verify_internal_ticket_from_envelope(raw_reply, required=True)
                        reply = ReplyEnvelope.model_validate(raw_reply)
                        if not reply.success:
                            self._raise_for_reply_error(reply)
                        return reply.payload
            raise GatewayError("RPC reply queue closed before a response was received")

    def _infer_message_type(self, action: str) -> MessageType:
        query_prefixes = ("get_", "list_", "fetch_", "search_", "find_")
        query_actions = {"list", "fetch_models", "get_config", "get_generation_params", "get_model_configs"}
        if action.startswith(query_prefixes) or action in query_actions:
            return "query"
        return "command"

    def _raise_for_reply_error(self, reply: ReplyEnvelope) -> None:
        error = reply.error
        message = f"Downstream action '{reply.action}' failed"
        status_code: Optional[int] = None
        if isinstance(error, dict):
            message = (
                error.get("message") or error.get("detail") or error.get("error") or message
            )
            raw_status = error.get("status_code") or error.get("code")
            if isinstance(raw_status, int):
                status_code = raw_status
        elif isinstance(error, str) and error.strip():
            message = error
        if status_code in (400, 422):
            raise ValidationError(message)
        if status_code == 404:
            raise NotFoundError(message)
        if status_code == 503:
            raise ServiceUnavailableError(message)
        raise GatewayError(message, details=reply.payload)
