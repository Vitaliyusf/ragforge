"""Canonical shared errors and compatibility helpers."""
from __future__ import annotations

import time
import traceback
from enum import Enum
from typing import Any, Dict, Mapping, Optional

from .context import get_context


class ErrorCode(str, Enum):
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    CONFLICT_ERROR = "CONFLICT_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    KAFKA_UNAVAILABLE = "KAFKA_UNAVAILABLE"
    KAFKA_TIMEOUT = "KAFKA_TIMEOUT"
    KAFKA_ERROR = "KAFKA_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_CONNECTION_ERROR = "DATABASE_CONNECTION_ERROR"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_READ_ERROR = "FILE_READ_ERROR"
    FILE_WRITE_ERROR = "FILE_WRITE_ERROR"
    FILE_PROCESSING_ERROR = "FILE_PROCESSING_ERROR"
    VECTOR_STORE_ERROR = "VECTOR_STORE_ERROR"
    INVALID_VECTOR = "INVALID_VECTOR"
    LLM_ERROR = "LLM_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_STREAMING_NOT_SUPPORTED = "LLM_STREAMING_NOT_SUPPORTED"
    EMBEDDING_ERROR = "EMBEDDING_ERROR"
    EMBEDDING_TIMEOUT = "EMBEDDING_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base structured application error."""

    error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR
    status_code: int = 500
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        error_code: Optional[ErrorCode] = None,
        details: Optional[Mapping[str, Any]] = None,
        original_exception: Optional[Exception] = None,
        status_code: Optional[int] = None,
        retryable: Optional[bool] = None,
        origin: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})
        self.original_exception = original_exception
        self.error_code = error_code or self.error_code
        if status_code is not None:
            self.status_code = status_code
        if retryable is not None:
            self.retryable = retryable
        self.origin = dict(origin or {})
        self.traceback = (
            "".join(traceback.format_exception(type(original_exception), original_exception, original_exception.__traceback__))
            if original_exception is not None
            else None
        )

    def to_dict(self, *, include_private: bool = False, location: Optional[str] = None) -> Dict[str, Any]:
        """Serialize the error into a stable dict."""
        origin = {
            **({"location": location} if location else {}),
            **self.origin,
        }
        payload: Dict[str, Any] = {
            "error": self.message,
            "message": self.message,
            "error_code": self.error_code.value,
            "code": self.error_code.value,
            "details": self.details,
            "origin": {key: value for key, value in origin.items() if value is not None},
            "retryable": self.retryable,
            "status_code": self.status_code,
            "timestamp": int(time.time() * 1000),
        }
        payload.update({key: value for key, value in get_context().items() if value is not None})
        if include_private and self.original_exception is not None:
            payload["cause"] = {
                "type": type(self.original_exception).__name__,
                "message": str(self.original_exception),
            }
            if self.traceback:
                payload["stack"] = self.traceback
        return payload


class ValidationError(AppError):
    error_code = ErrorCode.VALIDATION_ERROR
    status_code = 400


class NotFoundError(AppError):
    error_code = ErrorCode.NOT_FOUND
    status_code = 404


class AlreadyExistsError(AppError):
    error_code = ErrorCode.ALREADY_EXISTS
    status_code = 409


class AuthenticationError(AppError):
    error_code = ErrorCode.AUTHENTICATION_ERROR
    status_code = 401


class AuthorizationError(AppError):
    error_code = ErrorCode.AUTHORIZATION_ERROR
    status_code = 403


class ConflictError(AppError):
    error_code = ErrorCode.CONFLICT_ERROR
    status_code = 409


class RateLimitError(AppError):
    error_code = ErrorCode.RATE_LIMIT_ERROR
    status_code = 429
    retryable = True


class TimeoutException(AppError):
    error_code = ErrorCode.TIMEOUT_ERROR
    status_code = 504
    retryable = True


class ServiceException(AppError):
    error_code = ErrorCode.EXTERNAL_SERVICE_ERROR
    status_code = 503
    retryable = True


class ExternalServiceError(ServiceException):
    pass


class KafkaException(AppError):
    error_code = ErrorCode.KAFKA_ERROR
    status_code = 503
    retryable = True


class KafkaUnavailableError(KafkaException):
    error_code = ErrorCode.KAFKA_UNAVAILABLE


class DatabaseException(AppError):
    error_code = ErrorCode.DATABASE_ERROR
    status_code = 500


class InternalError(AppError):
    error_code = ErrorCode.INTERNAL_ERROR
    status_code = 500


def coerce_error(exception: Exception, *, location: Optional[str] = None, default_error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR) -> AppError:
    """Convert arbitrary exceptions into one canonical `AppError`."""
    if isinstance(exception, AppError):
        if location and "location" not in exception.origin:
            exception.origin["location"] = location
        return exception
    if isinstance(exception, TimeoutError):
        return TimeoutException(
            "Request timeout",
            details={"timeout_error": str(exception)},
            original_exception=exception,
            origin={"location": location},
        )
    if isinstance(exception, ValueError):
        return ValidationError(
            f"Validation error: {exception}",
            details={"validation_error": str(exception)},
            original_exception=exception,
            origin={"location": location},
        )
    if isinstance(exception, KeyError):
        return ValidationError(
            f"Missing required field: {exception}",
            details={"missing_field": str(exception)},
            original_exception=exception,
            origin={"location": location},
        )
    if isinstance(exception, RuntimeError):
        return ServiceException(
            "Service unavailable",
            details={"runtime_error": str(exception)},
            original_exception=exception,
            origin={"location": location},
        )
    return AppError(
        str(exception) or "An unexpected error occurred",
        error_code=default_error_code,
        details={"exception_type": type(exception).__name__},
        original_exception=exception,
        origin={"location": location} if location else None,
    )


def public_error_payload(
    exception: Exception,
    *,
    location: Optional[str] = None,
    include_private: bool = False,
    default_error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
) -> Dict[str, Any]:
    """Return the canonical serialized error payload."""
    return coerce_error(exception, location=location, default_error_code=default_error_code).to_dict(
        include_private=include_private,
        location=location,
    )
