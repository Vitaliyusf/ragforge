"""Application runtime composition for the memory service."""
import os
import time
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging_config import ServiceLogger
from app.messaging.factories import MessageQueueFactory
from app.messaging.implementations.rabbitmq import RabbitMQConsumerImpl
from app.services.chat_exit_service import ChatExitService
from app.services.chat_service import ChatService
from app.services.memory_handler_service import MemoryHandlerService
from app.services.memory_service import LongTermMemoryService
from app.services.message_service import MessageService
from app.db.session import ensure_tenant_indexes


class MemoryApplicationRuntime:
    """Encapsulates service wiring. Consumer is started in FastAPI lifespan."""

    def __init__(self):
        self.startup_time: int = 0
        self.logger = ServiceLogger(settings.service_name)
        self.consumer: RabbitMQConsumerImpl = MessageQueueFactory.create_consumer(settings)
        self.chat_service = ChatService(self.logger)
        self.message_service = MessageService(self.logger, self.chat_service)
        self.memory_service = LongTermMemoryService(self.logger)
        self.chat_exit_service = ChatExitService(
            self.chat_service,
            self.message_service,
            self.memory_service,
            self.logger,
        )
        self.handler = MemoryHandlerService(
            self.chat_service,
            self.message_service,
            self.memory_service,
            self.chat_exit_service,
            self.logger,
        )

    def should_start_background_consumers(self) -> bool:
        if not settings.enable_background_consumers:
            return False
        if os.getenv("PYTEST_CURRENT_TEST"):
            return False
        return True

    async def start(self) -> None:
        self.startup_time = int(time.time())
        self.logger.log("main:startup", "Memory service starting up")
        ensure_tenant_indexes()
        if not self.should_start_background_consumers():
            self.logger.log("main:startup", "Background consumers disabled")
            return
        await self.consumer.start(self._handle_message)
        self.logger.log("main:startup", "Memory RabbitMQ consumer started")

    async def _handle_message(
        self, body: Dict[str, Any], reply_to: str, correlation_id: str
    ) -> Optional[Dict[str, Any]]:
        """Route message to handler and return the reply envelope."""
        return await self.handler.process_request_async(body, reply_to, correlation_id)

    async def shutdown(self) -> None:
        self.logger.log("main:shutdown", "Memory service shutting down")
        await self.consumer.stop()
        self.logger.log("main:shutdown", "Memory service shutdown complete")

    def health_payload(self) -> dict:
        return {
            "status": "ok",
            "service": settings.service_name,
            "timestamp": int(time.time()),
            "checks": {
                "consumer": "ok" if self.consumer.is_connected() else "not_connected",
            },
        }
