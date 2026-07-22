"""Shared REST controller primitives."""
from typing import Callable, TypeVar

from fastapi import HTTPException

from app.core.errors import handle_service_error


T = TypeVar("T")


class EndpointController:
    """Base controller with shared exception translation."""

    def execute(self, operation: Callable[[], T]) -> T:
        """Run endpoint logic and normalize service errors into HTTP errors."""
        try:
            return operation()
        except HTTPException:
            raise
        except Exception as exc:
            raise handle_service_error(exc)
