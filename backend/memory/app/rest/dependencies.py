"""Dependency providers for the FastAPI transport layer."""
from app.core.config import settings
from app.core.logging_config import ServiceLogger
from app.services.chat_service import ChatService
from app.services.message_service import MessageService


class BaseDependencyProvider:
    """Base provider that owns shared dependency construction."""

    def get_logger(self) -> ServiceLogger:
        """Return a request-scoped logger."""
        return ServiceLogger(settings.service_name)


class ChatDependencyProvider(BaseDependencyProvider):
    """Provider for chat-related dependencies."""

    def get_chat_service(self) -> ChatService:
        """Return the chat service."""
        return ChatService(self.get_logger())


class MessageDependencyProvider(ChatDependencyProvider):
    """Provider for message-related dependencies."""

    def get_message_service(self) -> MessageService:
        """Return the message service."""
        return MessageService(self.get_logger(), self.get_chat_service())


class ServiceContainer(MessageDependencyProvider):
    """Aggregate dependency provider for the REST API."""


service_container = ServiceContainer()
