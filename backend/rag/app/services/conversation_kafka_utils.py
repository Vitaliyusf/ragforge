"""Transport-neutral envelope and LLM response normalization helpers."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.services.conversation_persistence import make_json_safe
from app.services.conversation_types import ConversationRequest


STRUCTURED_OUTPUT_DEBUG_PREFIX = "__structured_output_debug__:"


def build_message_envelope(
    *,
    message_type: str,
    action: str,
    source_service: str,
    target_service: str,
    request_id: Optional[str],
    trace_id: Optional[str],
    payload: Dict[str, Any],
    correlation_id: Optional[str] = None,
    reply_to: Optional[str] = None,
    stream_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the shared cross-service message envelope."""
    envelope: Dict[str, Any] = {
        "message_id": str(uuid4()),
        "message_type": message_type,
        "action": action,
        "source_service": source_service,
        "target_service": target_service,
        "request_id": request_id,
        "trace_id": trace_id,
        "correlation_id": correlation_id or str(uuid4()),
        "timestamp": int(time.time() * 1000),
        "payload": make_json_safe(payload),
    }
    if reply_to:
        envelope["reply_to"] = reply_to
    if stream_to:
        envelope["stream_to"] = stream_to
    return envelope


# Compatibility alias for older tests and private callers. Active RAG runtime
# code uses the transport-neutral name above.
build_kafka_envelope = build_message_envelope


def extract_message_payload(message: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a shared-envelope payload or legacy plain message."""
    if not isinstance(message, dict):
        return {}
    if isinstance(message.get("payload"), dict) and message.get("message_type") in {
        "command",
        "query",
        "reply",
        "event",
        "stream_event",
    }:
        payload = dict(message["payload"])
        for key in (
            "request_id",
            "trace_id",
            "correlation_id",
            "reply_to",
            "stream_to",
            "action",
            "source_service",
            "target_service",
            "message_type",
            "message_id",
            "timestamp",
        ):
            if message.get(key) is not None and key not in payload:
                payload[key] = message.get(key)
        return make_json_safe(payload)
    return make_json_safe(message)


def extract_reply_payload(message: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize a reply message into a payload dict."""
    if not isinstance(message, dict):
        return {}
    if message.get("message_type") == "reply":
        if message.get("success", True):
            payload = extract_message_payload(message)
            if message.get("source_service") == "llm_agent":
                return normalize_llm_agent_response(payload)
            return payload
        error = message.get("error") or "Service request failed"
        raise RuntimeError(str(error))
    data = message.get("data")
    if isinstance(data, dict):
        return make_json_safe(data)
    return extract_message_payload(message)


def extract_stream_event(message: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize streamed llm events from shared or legacy shapes."""
    event = extract_message_payload(message)
    if isinstance(event.get("data"), dict) and event.get("event_type"):
        event_type = event.get("event_type")
        data = event.get("data", {})
        if event_type == "llm.token":
            event["event"] = "delta"
            event["text_delta"] = data.get("token", "")
            event["token_index"] = data.get("index")
        elif event_type == "llm.done":
            event["event"] = "completed"
            event["finish_reason"] = data.get("finish_reason")
            event["token_count"] = data.get("token_count")
        elif event_type == "llm.error":
            event["event"] = "error"
            event["code"] = data.get("code")
            event["message"] = data.get("message")
    if isinstance(message, dict):
        if message.get("request_id") and "request_id" not in event:
            event["request_id"] = message["request_id"]
        if message.get("trace_id") and "trace_id" not in event:
            event["trace_id"] = message["trace_id"]
        if message.get("correlation_id") and "correlation_id" not in event:
            event["correlation_id"] = message["correlation_id"]
    return make_json_safe(event)


def message_role(message: Dict[str, Any]) -> str:
    """Normalize one conversation message role into llm-agent's typed contract."""
    role = str(message.get("role") or message.get("sender") or "user").lower()
    if role in {"assistant", "system", "tool", "user"}:
        return role
    if role in {"bot", "ai", "model"}:
        return "assistant"
    return "user"


def conversation_history(messages: Any) -> List[Dict[str, str]]:
    """Normalize rag recent messages into typed llm-agent conversation history."""
    if not isinstance(messages, list):
        return []
    history: List[Dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content") or message.get("message") or message.get("text") or ""
        if not content:
            continue
        history.append({"role": message_role(message), "content": str(content)})
    return history


def chunk_text_context(retrieved_chunks: Any) -> List[str]:
    """Extract chunk text strings for llm-agent typed inputs."""
    if not isinstance(retrieved_chunks, list):
        return []
    context: List[str] = []
    for chunk in retrieved_chunks:
        if not isinstance(chunk, dict):
            continue
        text = chunk.get("text") or chunk.get("chunk") or chunk.get("content") or ""
        if text:
            context.append(str(text))
    return context


def base_llm_metadata(request: ConversationRequest, **extras: Any) -> Dict[str, Any]:
    """Build shared llm-agent typed metadata for rag-originated requests."""
    metadata: Dict[str, Any] = {
        "conversation_id": request.conversation_id,
        "turn_id": request.turn_id,
        "request_id": request.request_id,
        "trace_id": request.trace_id,
        "graph_run_id": request.graph_run_id,
        "owner_id": request.owner_id,
        "owner_type": request.owner_type,
        "mode": request.mode,
    }
    for key, value in extras.items():
        if value is not None:
            metadata[key] = value
    return metadata


def normalize_llm_agent_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten typed llm-agent replies into the shapes currently used by the graph."""
    if not isinstance(payload, dict):
        return {}

    request_type = payload.get("request_type")
    parsed_output = payload.get("parsed_output")
    if not isinstance(parsed_output, dict):
        return payload

    structured_output_debug = _extract_structured_output_debug(payload.get("visible_reasoning_steps"))
    normalized = dict(parsed_output)
    normalized["status"] = payload.get("status")
    normalized["errors"] = payload.get("errors", [])
    normalized["trace"] = payload.get("trace", {})
    normalized["prompt_version"] = payload.get("prompt_version")
    normalized["raw_output"] = payload.get("raw_output", "")
    if structured_output_debug:
        normalized["_structured_output_debug"] = structured_output_debug

    if request_type == "answer_generation":
        normalized["answer"] = parsed_output.get("answer", payload.get("raw_output", ""))
        normalized["raw_output"] = payload.get("raw_output", normalized["answer"])
        normalized["model_name"] = payload.get("model")
        normalized["raw_prompt"] = payload.get("raw_prompt", "")
        normalized["system_prompt"] = payload.get("system_prompt", "")
        return normalized

    if request_type == "answer_evaluation":
        normalized["model_name"] = parsed_output.get("model_name") or payload.get("model")
        normalized["should_revise"] = parsed_output.get("verdict") == "revise"
        return normalized

    if request_type == "query_rewrite":
        normalized.setdefault("subqueries", [])
        normalized.setdefault("pass_two_hints", [])
        normalized.setdefault("decision", "rewrite")
        return normalized

    if request_type == "content_risk_scan":
        risk_level = str(parsed_output.get("risk_level", "")).lower()
        normalized["blocked"] = risk_level in {"high", "critical", "blocked"}
        normalized["message"] = parsed_output.get("summary", "")
        return normalized

    return normalized


def _extract_structured_output_debug(visible_reasoning_steps: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(visible_reasoning_steps, list):
        return None

    for step in visible_reasoning_steps:
        if not isinstance(step, str) or not step.startswith(STRUCTURED_OUTPUT_DEBUG_PREFIX):
            continue
        try:
            parsed = json.loads(step[len(STRUCTURED_OUTPUT_DEBUG_PREFIX):])
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None
