"""Synchronous adapter for RabbitMQ publishes from Kafka worker threads."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from shared.rabbitmq_base import BaseRabbitMQProducer
from shared.auth import attach_internal_auth_context

from app.messaging.interfaces import IProducer


class ThreadsafeRabbitMQPublisher(IProducer):
    """Bridge synchronous extraction handlers to the FastAPI event loop."""

    def __init__(
        self,
        producer: BaseRabbitMQProducer,
        loop: asyncio.AbstractEventLoop,
        timeout: float = 10.0,
    ) -> None:
        self._producer = producer
        self._loop = loop
        self._timeout = timeout

    def send(self, routing_key: str, message: Dict[str, Any]) -> None:
        future = asyncio.run_coroutine_threadsafe(
            self._producer.publish(routing_key, attach_internal_auth_context(message)),
            self._loop,
        )
        future.result(timeout=self._timeout)

    def flush(self) -> None:
        return None

    def is_connected(self) -> bool:
        return self._producer.is_connected()
