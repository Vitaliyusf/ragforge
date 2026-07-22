"""Shared context-local metadata for structured logging and error propagation."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Dict, Iterator, Optional

__all__ = [
    "Token",
    "set_context",
    "update_context",
    "get_context",
    "clear_context",
    "bound_context",
]


_FIELDS: Dict[str, ContextVar[Optional[str]]] = {
    "service": ContextVar("service", default=None),
    "environment": ContextVar("environment", default=None),
    "request_id": ContextVar("request_id", default=None),
    "trace_id": ContextVar("trace_id", default=None),
    "correlation_id": ContextVar("correlation_id", default=None),
    "route": ContextVar("route", default=None),
    "method": ContextVar("method", default=None),
    "topic": ContextVar("topic", default=None),
    "action": ContextVar("action", default=None),
    "user_id": ContextVar("user_id", default=None),
    "tenant_id": ContextVar("tenant_id", default=None),
    "role": ContextVar("role", default=None),
    "admin_id": ContextVar("admin_id", default=None),
    "session_id": ContextVar("session_id", default=None),
    "connection_id": ContextVar("connection_id", default=None),
}


def set_context(**values: Optional[str]) -> Dict[str, Token]:
    """Bind the provided values and return reset tokens."""
    tokens: Dict[str, Token] = {}
    for key, value in values.items():
        field = _FIELDS.get(key)
        if field is None:
            continue
        tokens[key] = field.set(value)
    return tokens


def update_context(**values: Optional[str]) -> None:
    """Update the active context without returning reset tokens."""
    for key, value in values.items():
        field = _FIELDS.get(key)
        if field is None or value is None:
            continue
        field.set(value)


def get_context() -> Dict[str, Any]:
    """Return the current context values, excluding null fields."""
    return {
        key: field.get()
        for key, field in _FIELDS.items()
        if field.get() is not None
    }


def clear_context(tokens: Optional[Dict[str, Token]] = None) -> None:
    """Reset the active context to a previous state or to empty values."""
    if tokens:
        for key, token in reversed(list(tokens.items())):
            field = _FIELDS.get(key)
            if field is not None:
                field.reset(token)
        return

    for field in _FIELDS.values():
        field.set(None)


@contextmanager
def bound_context(**values: Optional[str]) -> Iterator[Dict[str, Any]]:
    """Temporarily bind context values for one execution scope."""
    tokens = set_context(**values)
    try:
        yield get_context()
    finally:
        clear_context(tokens)
