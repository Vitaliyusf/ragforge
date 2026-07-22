"""Structured HTTP exception handlers for the gateway FastAPI app."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.constants import HTTP_ERROR_CODES
from app.core.correlation import REQUEST_ID_HEADER, TRACE_ID_HEADER, add_correlation_metadata, correlation_metadata
from shared.errors import ErrorCode, InternalError, coerce_error


# ── Private helpers ───────────────────────────────────────────────────────────

def _correlation_headers() -> dict[str, str]:
    metadata = correlation_metadata()
    headers: dict[str, str] = {}
    if "request_id" in metadata:
        headers[REQUEST_ID_HEADER] = metadata["request_id"]
    if "trace_id" in metadata:
        headers[TRACE_ID_HEADER] = metadata["trace_id"]
    return headers


def _structured_error_body(
    *,
    error: str,
    message: str,
    code: str,
    status_code: int,
    location: str,
    retryable: bool = False,
    details=None,
) -> dict:
    body = {
        "error": error,
        "message": message,
        "code": code,
        "origin": {"service": "gateway", "location": location},
        "retryable": retryable,
        "status_code": status_code,
    }
    if details is not None:
        body["details"] = details
    return add_correlation_metadata(body)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Return a consistent structured body for every HTTP error."""
    error_code = HTTP_ERROR_CODES.get(exc.status_code, "error")
    headers = dict(getattr(exc, "headers", None) or {})
    headers.update({k: v for k, v in _correlation_headers().items() if k not in headers})
    return JSONResponse(
        status_code=exc.status_code,
        content=_structured_error_body(
            error=error_code,
            message=str(exc.detail),
            code=error_code.upper(),
            status_code=exc.status_code,
            location="gateway:http_exception_handler",
            retryable=exc.status_code in {408, 429, 503, 504},
        ),
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return structured validation errors in the standard shape."""
    return JSONResponse(
        status_code=422,
        content=_structured_error_body(
            error="validation_error",
            message="Request validation failed",
            code=ErrorCode.VALIDATION_ERROR.value,
            status_code=422,
            location="gateway:validation_exception_handler",
            retryable=False,
            details=exc.errors(),
        ),
        headers=_correlation_headers(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return the gateway's compatibility error shape for unhandled failures."""
    logger = getattr(request.app.state, "service_logger", None)
    resolved = coerce_error(
        InternalError(
            "An unexpected error occurred",
            details={"exception_type": type(exc).__name__},
            original_exception=exc,
            origin={"service": "gateway"},
        ),
        location="gateway:unhandled_exception_handler",
    )
    if logger is not None:
        logger.error("gateway:unhandled_exception_handler", resolved.message, exc)
    return JSONResponse(
        status_code=resolved.status_code,
        content=_structured_error_body(
            error="internal_error",
            message=resolved.message,
            code=resolved.error_code.value,
            status_code=resolved.status_code,
            location="gateway:unhandled_exception_handler",
            retryable=resolved.retryable,
        ),
        headers=_correlation_headers(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all gateway exception handlers to the FastAPI app."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
