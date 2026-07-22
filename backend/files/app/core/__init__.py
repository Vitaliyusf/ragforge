"""Core utilities and exception handling."""
from app.core.errors import (
    BaseServiceException,
    ServiceException,
    DatabaseException,
    ValidationException,
    NotFoundException,
    ErrorCode,
    ExceptionHandler,
    handle_kafka_request
)

__all__ = [
    "BaseServiceException",
    "ServiceException",
    "DatabaseException",
    "ValidationException",
    "NotFoundException",
    "ErrorCode",
    "ExceptionHandler",
    "handle_kafka_request"
]
