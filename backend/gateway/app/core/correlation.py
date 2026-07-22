"""Correlation helpers for HTTP and backend RPC request handling."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple, Dict, TypeVar, overload
from uuid import uuid4

from starlette.datastructures import MutableHeaders

from app.core.request_context import get_request_context

REQUEST_ID_HEADER = "X-Request-ID"
TRACE_ID_HEADER = "X-Trace-ID"


def generate_request_id() -> str:
    """Generate a request identifier."""
    return str(uuid4())


def generate_trace_id() -> str:
    """Generate a trace identifier."""
    return str(uuid4())


def extract_correlation_headers(headers: Mapping[str, str]) -> Tuple[Optional[str], Optional[str]]:
    """Extract correlation headers from an incoming request."""
    request_id = headers.get(REQUEST_ID_HEADER) or headers.get(REQUEST_ID_HEADER.lower())
    trace_id = headers.get(TRACE_ID_HEADER) or headers.get(TRACE_ID_HEADER.lower())
    return request_id, trace_id


def ensure_correlation_ids(
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Tuple[str, str]:
    """Ensure both correlation identifiers exist."""
    return request_id or generate_request_id(), trace_id or generate_trace_id()


def apply_correlation_headers(message: dict[str, Any], request_id: str, trace_id: str) -> None:
    """Attach correlation headers to an ASGI response start message."""
    headers = MutableHeaders(scope=message)
    headers[REQUEST_ID_HEADER] = request_id
    headers[TRACE_ID_HEADER] = trace_id


def correlation_metadata() -> dict[str, str]:
    """Return correlation identifiers from the active request context."""
    context = get_request_context()
    metadata: dict[str, str] = {}
    request_id = context.get("request_id")
    trace_id = context.get("trace_id")
    if request_id:
        metadata["request_id"] = request_id
    if trace_id:
        metadata["trace_id"] = trace_id
    return metadata


_PayloadT = TypeVar("_PayloadT")


@overload
def add_correlation_metadata(payload: Dict[str, Any]) -> Dict[str, Any]: ...
@overload
def add_correlation_metadata(payload: _PayloadT) -> _PayloadT: ...
def add_correlation_metadata(payload: Any) -> Any:
    """Add correlation identifiers to dict-like payloads without overwriting existing values."""
    if not isinstance(payload, dict):
        return payload

    enriched = dict(payload)
    for key, value in correlation_metadata().items():
        enriched.setdefault(key, value)
    return enriched
