"""Canonical RabbitMQ request/reply helpers for the RAG service."""
from __future__ import annotations

import time
from typing import Any, Dict
from uuid import uuid4


def extract_request_payload(body: Dict[str, Any], correlation_id: str = "") -> Dict[str, Any]:
    """Extract business fields while preserving trusted transport identifiers."""
    payload = body.get("payload")
    request_data = dict(payload) if isinstance(payload, dict) else dict(body)
    for field in ("request_id", "trace_id", "correlation_id"):
        value = body.get(field)
        if value:
            request_data.setdefault(field, value)
    if correlation_id:
        request_data["correlation_id"] = correlation_id
    return request_data


def build_reply_envelope(
    body: Dict[str, Any],
    result: Dict[str, Any],
    correlation_id: str = "",
) -> Dict[str, Any]:
    """Wrap a graph result in the shared authenticated reply contract."""
    success = not bool(result.get("error"))
    payload = dict(result)
    payload.pop("error", None)
    reply: Dict[str, Any] = {
        "message_id": str(uuid4()),
        "message_type": "reply",
        "action": str(body.get("action") or "request"),
        "source_service": "rag",
        "target_service": str(body.get("source_service") or "gateway"),
        "request_id": str(body.get("request_id") or correlation_id or uuid4()),
        "trace_id": str(body.get("trace_id") or body.get("request_id") or correlation_id or uuid4()),
        "correlation_id": str(correlation_id or body.get("correlation_id") or uuid4()),
        "timestamp": int(time.time() * 1000),
        "success": success,
        "payload": payload,
    }
    if not success:
        reply["error"] = {
            "code": "rag_execution_error",
            "message": "RAG request could not be completed",
        }
    return reply
