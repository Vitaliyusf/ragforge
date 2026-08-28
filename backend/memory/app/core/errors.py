"""Memory error compatibility layer backed by shared structured errors."""
import sys
from pathlib import Path
from typing import NoReturn, Union

from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.append(str(_BACKEND_ROOT))

from shared.errors import *  # noqa: F401,F403
from shared.errors import AppError, DatabaseError, ErrorCode, coerce_error


_PUBLIC_INTERNAL_MESSAGE = "Internal service error"


def raise_database_failure(operation: str, error: Exception) -> NoReturn:
    """Raise one safe database error while retaining the private cause."""
    if isinstance(error, AppError):
        raise error
    raise DatabaseError(
        "Database operation failed",
        details={"operation": operation},
        original_exception=error,
    ) from error


def public_service_error(error: Union[str, Exception]) -> dict[str, object]:
    """Build the bounded error fields exposed by Memory transports."""
    caller_message = error if isinstance(error, str) else None
    resolved = coerce_error(error if isinstance(error, Exception) else AppError(error))
    message = resolved.message
    if caller_message is not None:
        message = caller_message
    elif resolved.error_code in {ErrorCode.UNKNOWN_ERROR, ErrorCode.INTERNAL_ERROR}:
        message = _PUBLIC_INTERNAL_MESSAGE
    return {
        "message": message,
        "code": resolved.error_code.value,
        "retryable": resolved.retryable,
    }


def handle_service_error(error: Exception) -> HTTPException:
    """Convert memory-service errors to HTTP exceptions."""
    resolved = coerce_error(error)
    payload = public_service_error(resolved)
    return HTTPException(status_code=resolved.status_code, detail=payload)
