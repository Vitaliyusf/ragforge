"""Compatibility wrapper over the shared request context helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional

from shared.context import Token, clear_context, get_context, set_context, update_context


def set_request_context(
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    route: Optional[str] = None,
    method: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Token]:
    """Bind request metadata to the current context and return reset tokens."""
    return set_context(
        request_id=request_id,
        trace_id=trace_id,
        route=route,
        method=method,
        correlation_id=correlation_id,
    )


def update_request_context(
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    route: Optional[str] = None,
    method: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Update request metadata for the active context."""
    update_context(
        request_id=request_id,
        trace_id=trace_id,
        route=route,
        method=method,
        correlation_id=correlation_id,
    )


def get_request_context() -> Dict[str, Any]:
    """Return the current request metadata."""
    return get_context()


def clear_request_context(tokens: Optional[Dict[str, Token]] = None) -> None:
    """Reset request metadata to a previous or empty state."""
    clear_context(tokens)
