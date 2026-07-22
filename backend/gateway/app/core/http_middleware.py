"""HTTP middleware for request correlation and structured access logging."""
from __future__ import annotations

import time
from typing import Any, Callable

from starlette.datastructures import Headers

from app.core.correlation import (
    apply_correlation_headers,
    ensure_correlation_ids,
    extract_correlation_headers,
)
from app.core.request_context import clear_request_context, set_request_context, update_request_context


class CorrelationMiddleware:
    """ASGI middleware that manages correlation ids and emits one access log per request."""

    def __init__(self, app: Callable[..., Any]):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming_request_id, incoming_trace_id = extract_correlation_headers(headers)
        request_id, trace_id = ensure_correlation_ids(incoming_request_id, incoming_trace_id)
        method = scope.get("method", "UNKNOWN")
        route = scope.get("path", "")
        start_time = time.perf_counter()
        status_code = 500

        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        scope["state"]["trace_id"] = trace_id
        scope["state"]["route"] = route
        scope["state"]["method"] = method

        tokens = set_request_context(
            request_id=request_id,
            trace_id=trace_id,
            route=route,
            method=method,
        )

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]
                apply_correlation_headers(message, request_id, trace_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            resolved_route = getattr(scope.get("route"), "path", route)
            scope["state"]["route"] = resolved_route
            update_request_context(route=resolved_route)
            self._log_request(scope, request_id, trace_id, resolved_route, method, status_code, start_time)
            clear_request_context(tokens)
            raise

        resolved_route = getattr(scope.get("route"), "path", route)
        scope["state"]["route"] = resolved_route
        update_request_context(route=resolved_route)
        self._log_request(scope, request_id, trace_id, resolved_route, method, status_code, start_time)
        clear_request_context(tokens)

    def _log_request(
        self,
        scope: dict[str, Any],
        request_id: str,
        trace_id: str,
        route: str,
        method: str,
        status_code: int,
        start_time: float,
    ) -> None:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger = getattr(getattr(scope.get("app"), "state", None), "service_logger", None)
        if logger is None:
            return

        logger.access(
            route=route,
            method=method,
            status_code=status_code,
            latency_ms=latency_ms,
            request_id=request_id,
            trace_id=trace_id,
        )
