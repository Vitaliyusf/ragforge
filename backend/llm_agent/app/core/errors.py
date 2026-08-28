"""LLM-owned errors plus canonical cross-service error imports."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from shared.errors import (
    AppError as BaseServiceException,
    ErrorCode,
    NotFoundError as NotFoundException,
    ServiceException,
    TimeoutException,
    ValidationError as ValidationException,
)


class StreamingNotSupportedException(BaseServiceException):
    """Raised when an LLM provider cannot stream tokens."""

    error_code = ErrorCode.LLM_STREAMING_NOT_SUPPORTED
    status_code = 400

    def __init__(
        self,
        message: str,
        details: Optional[Mapping[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message,
            details=details,
            original_exception=original_exception,
        )


__all__ = [
    "BaseServiceException",
    "ErrorCode",
    "NotFoundException",
    "ServiceException",
    "StreamingNotSupportedException",
    "TimeoutException",
    "ValidationException",
]
