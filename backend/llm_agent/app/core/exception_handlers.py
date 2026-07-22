"""FastAPI exception handler registration for the llm_agent service."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import BaseServiceException


def register_exception_handlers(app: FastAPI) -> None:
    """Register all application-level exception handlers on *app*.

    Call once during app construction, before lifespan runs.
    """

    @app.exception_handler(BaseServiceException)
    async def service_exception_handler(
        request: Request, exc: BaseServiceException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=getattr(exc, "status_code", 500),
            content={
                "error": exc.message,
                "code": exc.error_code.value if hasattr(exc, "error_code") else "SERVICE_ERROR",
                "details": getattr(exc, "details", {}),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "Request validation failed",
                "code": "VALIDATION_ERROR",
                "details": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "code": "INTERNAL_ERROR",
                "detail": str(exc),
            },
        )
