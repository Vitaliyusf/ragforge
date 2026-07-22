"""Canonical shared errors and compatibility helpers."""
from __future__ import annotations

import time
import traceback
from contextlib import contextmanager
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Iterator, Mapping, Optional, cast
from uuid import uuid4

from fastapi import HTTPException

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


class FileProcessingError(AppError):
    error_code = ErrorCode.FILE_PROCESSING_ERROR
    status_code = 500


class VectorStoreError(AppError):
    error_code = ErrorCode.VECTOR_STORE_ERROR
    status_code = 500


class InvalidVectorError(ValidationError):
    error_code = ErrorCode.INVALID_VECTOR


class LLMError(AppError):
    error_code = ErrorCode.LLM_ERROR
    status_code = 503
    retryable = True


class EmbeddingError(AppError):
    error_code = ErrorCode.EMBEDDING_ERROR
    status_code = 503
    retryable = True


class InternalError(AppError):
    error_code = ErrorCode.INTERNAL_ERROR
    status_code = 500


BaseServiceException = AppError
GatewayError = AppError
ValidationException = ValidationError
NotFoundException = NotFoundError
ServiceUnavailableError = ServiceException
KafkaError = KafkaException
KafkaConnectionError = KafkaUnavailableError
KafkaTimeoutError = TimeoutException
DatabaseError = DatabaseException
MemoryServiceError = AppError
ChatNotFoundError = NotFoundError
MessageNotFoundError = NotFoundError
VectorDBError = VectorStoreError
VectorNotFoundError = NotFoundError


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


class ExceptionHandler:
    """Compatibility exception handler backed by the shared error model."""

    def __init__(
        self,
        logger: Optional[Any] = None,
        default_error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        log_traceback: bool = True,
    ) -> None:
        self.logger = logger
        self.default_error_code = default_error_code
        self.log_traceback = log_traceback

    def handle(
        self,
        exception: Exception,
        location: str = "unknown",
        context: Optional[Dict[str, Any]] = None,
        reraise: bool = False,
    ) -> Dict[str, Any]:
        app_error = coerce_error(exception, location=location, default_error_code=self.default_error_code)
        payload = app_error.to_dict(include_private=self.log_traceback, location=location)
        if context:
            payload.update({key: value for key, value in context.items() if value is not None})
        if self.logger:
            self.logger.error(location, payload["message"], app_error, data=context or {})
        if reraise:
            raise app_error
        return payload

    def handle_kafka_response(
        self,
        exception: Exception,
        correlation_id: str,
        producer: Optional[Any] = None,
        response_topic: Optional[str] = None,
        location: str = "unknown",
        request_context: Optional[Mapping[str, Any]] = None,
        source_service: str = "unknown",
    ) -> None:
        payload = self.handle(exception, location, {"correlation_id": correlation_id})
        if not (producer and response_topic and correlation_id):
            return
        try:
            producer.send(
                response_topic,
                build_kafka_error_response(
                    payload=payload,
                    correlation_id=correlation_id,
                    request_context=request_context or {},
                    source_service=source_service,
                ),
            )
            producer.flush()
        except Exception as send_error:
            if self.logger:
                self.logger.error(location, "Failed to send error response", send_error, data={"correlation_id": correlation_id})

    def handle_http_response(
        self,
        exception: Exception,
        location: str = "unknown",
        status_code: int = 500,
        default_message: str = "Internal server error",
    ) -> HTTPException:
        payload = self.handle(exception, location)
        resolved_error = coerce_error(exception, location=location, default_error_code=self.default_error_code)
        return HTTPException(status_code=getattr(resolved_error, "status_code", status_code), detail=payload.get("message", default_message))


def build_kafka_error_response(
    *,
    payload: Mapping[str, Any],
    correlation_id: str,
    request_context: Mapping[str, Any],
    source_service: str,
) -> Dict[str, Any]:
    """Build either a typed or legacy Kafka error reply based on the request context."""
    if request_context.get("message_type") or request_context.get("source_service") or request_context.get("reply_to"):
        return {
            "message_id": str(uuid4()),
            "message_type": "reply",
            "action": request_context.get("action") or "error",
            "source_service": source_service,
            "target_service": request_context.get("source_service") or "gateway",
            "request_id": request_context.get("request_id"),
            "trace_id": request_context.get("trace_id"),
            "correlation_id": correlation_id,
            "timestamp": int(time.time() * 1000),
            "payload": {},
            "success": False,
            "error": dict(payload),
        }

    return {
        "correlation_id": correlation_id,
        "data": dict(payload),
    }


def handle_exceptions(
    handler: Optional[ExceptionHandler] = None,
    error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
    log_location: Optional[str] = None,
    reraise: bool = False,
    return_error_dict: bool = False,
    send_kafka_response: bool = False,
    response_topic: Optional[str] = None,
    correlation_id_extractor: Optional[Callable] = None,
    producer_extractor: Optional[Callable] = None,
) -> Callable[[Callable], Callable]:
    """Decorate sync or async call sites with centralized exception handling."""

    def decorator(func: Callable) -> Callable:
        def _resolve_handler(args: tuple[Any, ...]) -> ExceptionHandler:
            if handler is not None:
                return handler
            if args and hasattr(args[0], "exception_handler"):
                return cast(ExceptionHandler, args[0].exception_handler)
            if args and hasattr(args[0], "logger"):
                return ExceptionHandler(logger=args[0].logger, default_error_code=error_code)
            return ExceptionHandler(default_error_code=error_code)

        def _context_from_call(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Dict[str, Any]:
            context: Dict[str, Any] = {}
            if correlation_id_extractor:
                try:
                    context["correlation_id"] = correlation_id_extractor(*args, **kwargs)
                except Exception:
                    pass
            return context

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            exc_handler = _resolve_handler(args)
            location = log_location or f"{func.__module__}.{func.__name__}"
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                context = _context_from_call(args, kwargs)
                error_response = exc_handler.handle(exc, location=location, context=context)
                if send_kafka_response:
                    producer = producer_extractor(*args, **kwargs) if producer_extractor else getattr(args[0], "producer", None) if args else None
                    request_context = kwargs.get("request") or (args[1] if len(args) > 1 and isinstance(args[1], dict) else {})
                    exc_handler.handle_kafka_response(
                        exc,
                        context.get("correlation_id") or "unknown",
                        producer=producer,
                        response_topic=response_topic,
                        location=location,
                        request_context=request_context,
                        source_service=getattr(getattr(args[0], "config", None), "service_name", "unknown") if args else "unknown",
                    )
                if return_error_dict:
                    return error_response
                if reraise:
                    raise coerce_error(exc, location=location, default_error_code=error_code)
                return None

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            exc_handler = _resolve_handler(args)
            location = log_location or f"{func.__module__}.{func.__name__}"
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as exc:
                context = _context_from_call(args, kwargs)
                error_response = exc_handler.handle(exc, location=location, context=context)
                if return_error_dict:
                    return error_response
                if reraise:
                    raise coerce_error(exc, location=location, default_error_code=error_code)
                raise exc_handler.handle_http_response(exc, location=location)

        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper

    return decorator


@contextmanager
def exception_context(
    handler: Optional[ExceptionHandler] = None,
    location: str = "unknown",
    context: Optional[Dict[str, Any]] = None,
    reraise: bool = False,
    on_error: Optional[Callable] = None,
) -> Iterator[ExceptionHandler]:
    """Context manager variant of `ExceptionHandler.handle`."""
    exc_handler = handler or ExceptionHandler()
    try:
        yield exc_handler
    except Exception as exc:
        error_response = exc_handler.handle(exc, location=location, context=context or {})
        if on_error:
            on_error(exc, error_response)
        if reraise:
            raise coerce_error(exc, location=location)


def handle_kafka_request(
    handler: Optional[ExceptionHandler] = None,
    response_topic: Optional[str] = None,
    correlation_id_key: str = "correlation_id",
) -> Callable[[Callable], Callable]:
    """Compatibility decorator for Kafka handlers."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            exc_handler = handler or getattr(args[0], "exception_handler", None) or ExceptionHandler(
                logger=getattr(args[0], "logger", None) if args else None
            )
            request = args[1] if len(args) > 1 and isinstance(args[1], dict) else kwargs.get("request", {})
            correlation_id = request.get(correlation_id_key, "unknown")
            topic = request.get("reply_to") or response_topic
            if topic is None and args:
                topic = getattr(getattr(args[0], "config", None), "response_topic", None)
            producer = getattr(args[0], "producer", None) if args else None
            source_service = getattr(getattr(args[0], "config", None), "service_name", "unknown") if args else "unknown"
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                exc_handler.handle_kafka_response(
                    exc,
                    correlation_id,
                    producer=producer,
                    response_topic=topic,
                    location=f"{func.__module__}.{func.__name__}",
                    request_context=request,
                    source_service=source_service,
                )
                return None

        return wrapper

    return decorator


def handle_http_endpoint(
    handler: Optional[ExceptionHandler] = None, status_code: int = 500
) -> Callable[[Callable], Callable]:
    """Compatibility decorator for FastAPI endpoints."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            exc_handler = handler or getattr(args[0], "exception_handler", None) or ExceptionHandler(
                logger=getattr(args[0], "logger", None) if args else None
            )
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as exc:
                raise exc_handler.handle_http_response(exc, f"{func.__module__}.{func.__name__}", status_code)

        return async_wrapper

    return decorator
