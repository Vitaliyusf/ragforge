"""Files-service error formatting built on the shared error contract."""
from __future__ import annotations

from typing import Any, Dict, Optional

from shared.errors import ErrorCode, coerce_error


class ExceptionHandler:
    """Format Files transport errors and log their private diagnostics."""

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
        error = coerce_error(
            exception,
            location=location,
            default_error_code=self.default_error_code,
        )
        payload = error.to_dict(
            include_private=self.log_traceback,
            location=location,
        )
        if context:
            payload.update({key: value for key, value in context.items() if value is not None})
        if self.logger:
            self.logger.error(location, payload["message"], error, data=context or {})
        if reraise:
            raise error
        return payload
