"""Exception types re-exported from the shared errors module."""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.append(str(_BACKEND_ROOT))

from shared.errors import (  # noqa: E402
    BaseServiceException,
    ServiceException,
    KafkaException,
    DatabaseException,
    ValidationException,
    NotFoundException,
    TimeoutException,
    ErrorCode,
    ExceptionHandler,
    handle_exceptions,
    handle_kafka_request,
    handle_http_endpoint,
    exception_context,
)

__all__ = [
    "BaseServiceException",
    "ServiceException",
    "KafkaException",
    "DatabaseException",
    "ValidationException",
    "NotFoundException",
    "TimeoutException",
    "ErrorCode",
    "ExceptionHandler",
    "handle_exceptions",
    "handle_kafka_request",
    "handle_http_endpoint",
    "exception_context",
]
