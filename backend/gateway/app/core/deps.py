"""FastAPI dependency-injection getters for all gateway service singletons.

Route modules import from here instead of from ``app.main`` directly, keeping
the deferred-import pattern in a single place.
"""
from __future__ import annotations

from typing import Optional, TypeVar

from app.core.config import GatewayConfig
from app.core.logging_config import ServiceLogger
from app.core.rabbitmq_client import RabbitMQClient
from app.services.chat_history_service import ChatHistoryService
from app.services.chat_service import ChatService
from app.services.config_management_service import ConfigManagementService
from app.services.file_service import FileService
from app.services.log_service import LogService
from app.services.long_term_memory_service import LongTermMemoryService
from app.services.model_management_service import ModelManagementService
from app.services.rag_service import RagService
from app.services.auth_service import AuthService

_T = TypeVar("_T")


def _require(value: Optional[_T], name: str) -> _T:
    """Raise ``RuntimeError`` when a service singleton has not been initialised."""
    if value is None:
        raise RuntimeError(f"{name} not initialized")
    return value


# ── Getters (called via FastAPI Depends()) ────────────────────────────────────

def get_config() -> GatewayConfig:
    from app.main import _config
    return _require(_config, "Configuration")


def get_auth_service() -> AuthService:
    from app.main import _auth_service
    return _require(_auth_service, "Authentication service")


def get_logger() -> ServiceLogger:
    from app.main import _logger
    return _require(_logger, "Logger")


def get_rabbitmq_client() -> RabbitMQClient:
    from app.main import _rabbitmq_client
    return _require(_rabbitmq_client, "RabbitMQ client")


def get_chat_service() -> ChatService:
    from app.main import _chat_service
    return _require(_chat_service, "Chat service")


def get_file_service() -> FileService:
    from app.main import _file_service
    return _require(_file_service, "File service")


def get_chat_history_service() -> ChatHistoryService:
    from app.main import _chat_history_service
    return _require(_chat_history_service, "Chat history service")


def get_long_term_memory_service() -> LongTermMemoryService:
    from app.main import _long_term_memory_service
    return _require(_long_term_memory_service, "Long-term memory service")


def get_log_service() -> LogService:
    from app.main import _log_service
    return _require(_log_service, "Log service")


def get_rag_service() -> RagService:
    from app.main import _rag_service
    return _require(_rag_service, "RAG service")


def get_config_management_service() -> ConfigManagementService:
    from app.main import _config_management_service
    return _require(_config_management_service, "Config management service")


def get_model_management_service() -> ModelManagementService:
    from app.main import _model_management_service
    return _require(_model_management_service, "Model management service")
