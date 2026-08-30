"""Shared async RabbitMQ consumer and producer base classes.

All RPC services subclass these. The embedding pipeline continues to use
kafka_base.py — this module does not replace it.

Usage in a service::

    from shared.rabbitmq_base import BaseRabbitMQConsumer, BaseRabbitMQProducer

    class RabbitMQConsumerImpl(BaseRabbitMQConsumer):
        pass

    class RabbitMQProducerImpl(BaseRabbitMQProducer):
        pass
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol, runtime_checkable

import aio_pika
import aio_pika.abc

from .auth import (
    AuthError,
    AuthIdentity,
    ROLE_SERVICE,
    attach_internal_auth_context,
    verify_internal_ticket_from_envelope,
)
from .context import bound_context
from .metrics import METRICS

logger = logging.getLogger(__name__)


@runtime_checkable
class RabbitMQSettings(Protocol):
    """Structural interface every RPC service config must satisfy."""
    rabbitmq_url: str
    rabbitmq_exchange: str
    rabbitmq_queue: str
    rabbitmq_prefetch_count: int


HandlerFn = Callable[
    [Dict[str, Any], str, str],
    Awaitable[Optional[Dict[str, Any]]],
]


class BaseRabbitMQConsumer:
    """Async RabbitMQ consumer for FastAPI lifespan integration.

    Call ``start(handler)`` in the lifespan startup block.
    Call ``stop()`` in the lifespan shutdown block.

    The handler receives ``(body, reply_to, correlation_id)`` and returns a
    reply dict (published automatically) or ``None`` (no reply sent).
    On handler exception the message is nacked with ``requeue=False`` so the
    broker routes it to the dead-letter queue if one is configured.
    """

    def __init__(self, config: RabbitMQSettings) -> None:
        self.config = config
        self._connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
        self._channel: Optional[aio_pika.abc.AbstractChannel] = None

    async def start(self, handler: HandlerFn) -> None:
        """Connect, declare queue, and begin consuming."""
        self._connection = await aio_pika.connect_robust(self.config.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.config.rabbitmq_prefetch_count)

        exchange = await self._channel.declare_exchange(
            self.config.rabbitmq_exchange,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        queue = await self._channel.declare_queue(
            self.config.rabbitmq_queue,
            durable=True,
            arguments={"x-dead-letter-exchange": f"{self.config.rabbitmq_exchange}.dlq"},
        )
        await queue.bind(exchange, routing_key=self.config.rabbitmq_queue)

        async def _on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
            await self._dispatch(message, handler)

        await queue.consume(_on_message)
        logger.info("RabbitMQ consumer started on queue '%s'", self.config.rabbitmq_queue)

    async def _dispatch(
        self,
        message: aio_pika.abc.AbstractIncomingMessage,
        handler: HandlerFn,
    ) -> None:
        """Process one message: call handler, publish reply if returned, nack on error."""
        # Consumer-side saturation, recorded at the one boundary every RPC
        # service already shares rather than in each service separately.
        # `queue` is the declared queue name from config, so the series stays
        # bounded by the topology and never by message content.
        service = str(getattr(self.config, "service_name", "unknown"))
        queue_name = self.config.rabbitmq_queue
        METRICS.rabbitmq_deliveries_total.labels(service=service, queue=queue_name).inc()
        inflight = METRICS.rabbitmq_inflight_deliveries.labels(service=service, queue=queue_name)
        inflight.inc()
        try:
            await self._dispatch_message(message, handler)
        finally:
            # `finally`, so a handler that raises into the nack path still
            # releases the gauge. One that only decrements on success drifts
            # upward forever and reads as permanent saturation.
            inflight.dec()

    async def _dispatch_message(
        self,
        message: aio_pika.abc.AbstractIncomingMessage,
        handler: HandlerFn,
    ) -> None:
        async with message.process(requeue=False):
            body = json.loads(message.body)
            reply_to = message.reply_to or ""
            correlation_id = message.correlation_id or ""

            # Propagate trace context from the envelope so every log line
            # emitted during handler execution carries the originating IDs.
            ctx: Dict[str, Optional[str]] = {}
            if isinstance(body, dict):
                if body.get("request_id"):
                    ctx["request_id"] = body["request_id"]
                if body.get("trace_id"):
                    ctx["trace_id"] = body["trace_id"]
                ctx["traffic_class"] = "eval" if body.get("traffic_class") == "eval" else "live"
            if correlation_id:
                ctx["correlation_id"] = correlation_id

            try:
                identity = verify_internal_ticket_from_envelope(body)
            except AuthError as exc:
                await self._handle_auth_failure(exc, reply_to, correlation_id)
                return
            if identity is not None:
                ctx.update(identity.to_dict())

            with bound_context(**ctx):
                try:
                    reply = await handler(body, reply_to, correlation_id)
                    if reply is not None and reply_to and self._channel is not None:
                        attach_internal_auth_context(reply)
                        await self._channel.default_exchange.publish(
                            aio_pika.Message(
                                body=json.dumps(reply).encode(),
                                correlation_id=correlation_id,
                                content_type="application/json",
                            ),
                            routing_key=reply_to,
                        )
                except Exception:
                    logger.exception(
                        "Handler failed for message on queue '%s'", self.config.rabbitmq_queue
                    )
                    raise  # triggers nack via message.process(requeue=False)

    async def _handle_auth_failure(
        self,
        error: AuthError,
        reply_to: str,
        correlation_id: str,
    ) -> None:
        """Return a safe, authenticated RPC error or nack fire-and-forget input."""
        code = error.code
        logger.warning(
            "Internal RPC auth failure on queue '%s' (code=%s)",
            self.config.rabbitmq_queue,
            code,
        )
        if not reply_to or not correlation_id:
            raise error
        if self._channel is None:
            logger.error(
                "Auth failure reply could not be sent on queue '%s' (code=%s)",
                self.config.rabbitmq_queue,
                code,
            )
            raise error

        reply: Dict[str, Any] = {
            "message_type": "reply",
            "source_service": self.config.rabbitmq_queue,
            "correlation_id": correlation_id,
            "success": False,
            "payload": {},
            "error": {
                "code": code,
                "message": {
                    "internal_auth_expired": "Internal authentication context expired",
                    "internal_auth_required": "Internal authentication context required",
                }.get(code, "Internal authentication context invalid"),
            },
        }
        service_identity = AuthIdentity(
            tenant_id="internal",
            user_id=f"{self.config.rabbitmq_queue}-service",
            role=ROLE_SERVICE,
        )
        try:
            attach_internal_auth_context(reply, identity=service_identity)
            await self._channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(reply).encode(),
                    correlation_id=correlation_id,
                    content_type="application/json",
                ),
                routing_key=reply_to,
            )
        except Exception:
            logger.exception(
                "Auth failure reply could not be sent on queue '%s' (code=%s)",
                self.config.rabbitmq_queue,
                code,
            )
            raise
        logger.info(
            "Auth failure reply sent on queue '%s' (code=%s)",
            self.config.rabbitmq_queue,
            code,
        )

    async def stop(self) -> None:
        """Close the connection gracefully."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        logger.info("RabbitMQ consumer stopped (queue '%s')", self.config.rabbitmq_queue)

    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed


class BaseRabbitMQProducer:
    """Async RabbitMQ producer for RPC replies and fire-and-forget commands."""

    def __init__(self, config: RabbitMQSettings) -> None:
        self.config = config
        self._connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
        self._channel: Optional[aio_pika.abc.AbstractChannel] = None
        self._exchange: Optional[aio_pika.abc.AbstractExchange] = None

    async def connect(self) -> None:
        """Establish connection and declare the shared exchange."""
        self._connection = await aio_pika.connect_robust(self.config.rabbitmq_url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            self.config.rabbitmq_exchange,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

    async def reply(self, reply_to: str, correlation_id: str, body: Dict[str, Any]) -> None:
        """Send a reply directly to an exclusive reply queue (default exchange)."""
        if self._channel is None:
            raise RuntimeError("RabbitMQ channel is not connected")
        attach_internal_auth_context(body)
        await self._channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(body).encode(),
                correlation_id=correlation_id,
                content_type="application/json",
            ),
            routing_key=reply_to,
        )

    async def publish(self, routing_key: str, body: Dict[str, Any]) -> None:
        """Publish a command to the shared exchange."""
        if self._exchange is None:
            raise RuntimeError("RabbitMQ exchange is not connected")
        attach_internal_auth_context(body)
        await self._exchange.publish(
            aio_pika.Message(
                body=json.dumps(body).encode(),
                content_type="application/json",
            ),
            routing_key=routing_key,
        )

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()

    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed
