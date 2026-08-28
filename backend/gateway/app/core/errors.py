"""Gateway error compatibility layer backed by shared structured errors."""
from __future__ import annotations

from fastapi import HTTPException, status

from shared.errors import (
    AppError,
    NotFoundError,
    ServiceException as ServiceUnavailableError,
    TimeoutException as RPCTimeoutError,
    ValidationError,
    coerce_error,
)

RPCConnectionError = ServiceUnavailableError

try:
    from shared.circuit_breaker import CircuitBreakerOpen
    _HAS_CIRCUIT_BREAKER = True
except ImportError:
    CircuitBreakerOpen = None  # type: ignore[assignment, misc]
    _HAS_CIRCUIT_BREAKER = False


GatewayError = AppError


def map_exception_to_http(exception: Exception) -> HTTPException:
    """Map shared errors without exposing backend details on server failures."""
    if _HAS_CIRCUIT_BREAKER and isinstance(exception, CircuitBreakerOpen):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
            headers={"Retry-After": str(int(exception.remaining_seconds) + 1)},
        )

    error = coerce_error(exception)
    if error.status_code < 500:
        detail = error.message
    elif error.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        detail = "Service temporarily unavailable"
    elif error.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
        detail = "Request timed out"
    else:
        detail = "An unexpected error occurred"
    return HTTPException(status_code=error.status_code, detail=detail)


def handle_exception(exception: Exception) -> HTTPException:
    """Return the mapped FastAPI exception for one backend exception."""
    return map_exception_to_http(exception)


__all__ = [
    "GatewayError",
    "RPCConnectionError",
    "RPCTimeoutError",
    "NotFoundError",
    "ServiceUnavailableError",
    "ValidationError",
    "handle_exception",
    "map_exception_to_http",
]
