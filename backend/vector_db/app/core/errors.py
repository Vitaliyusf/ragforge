"""Vector-owned errors and HTTP mapping built on shared contracts."""

from fastapi import HTTPException

from shared.errors import AppError, ErrorCode, ValidationError, coerce_error


class VectorStoreError(AppError):
    """Raised when the vector store cannot complete an operation."""

    error_code = ErrorCode.VECTOR_STORE_ERROR


class InvalidVectorError(ValidationError):
    """Raised when a vector request is invalid."""

    error_code = ErrorCode.INVALID_VECTOR


def handle_vector_db_error(error: Exception) -> HTTPException:
    """Convert vector DB errors to HTTP exceptions."""
    resolved = coerce_error(error)
    return HTTPException(status_code=resolved.status_code, detail=resolved.message)
