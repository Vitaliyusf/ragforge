"""Bounded, durable metadata contract for persisted chat messages."""
from __future__ import annotations

import json
import re
from typing import Any, Dict

MAX_METADATA_BYTES = 65_536
MAX_ITEMS = 40
MAX_STRING_LENGTH = 4_000
MAX_DEPTH = 5

_PRIVATE_KEY = re.compile(r"auth|credential|password|secret|session|token", re.IGNORECASE)
_TOP_LEVEL_KEYS = {
    "requestId",
    "traceId",
    "conversationId",
    "turnId",
    "mode",
    "answerReview",
    "sources",
    "retrievalSummary",
    "traceEvents",
    "debugPayloads",
    "feedback",
}
_SOURCE_KEYS = {
    "file_id",
    "document_id",
    "chunk_id",
    "chunk_index",
    "chunk_version",
    "source_name",
    "source",
    "filename",
    "title",
    "page",
    "score",
    "similarity",
    "retrieval_allowed",
    "review_status",
    "issue_flags",
    "created_at",
    "text_preview",
}
_DEBUG_KEYS = {
    "generation_instructions",
    "rewrite_response",
    "system_prompt",
    "raw_prompt",
    "visible_reasoning_summary",
    "visible_reasoning_steps",
    "input_safety_flags",
    "raw_input_safety_flags",
    "output_safety_flags",
    "raw_output_safety_flags",
    "raw_output",
    "output_safety_structured_output_candidates",
    "output_safety_structured_output_selected_index",
    "output_safety_structured_output_selection_policy",
    "output_safety_structured_output_extraction_mode",
    "output_safety_raw_output",
}


def _bounded_json(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_STRING_LENGTH]
    if depth >= MAX_DEPTH:
        return None
    if isinstance(value, list):
        return [_bounded_json(item, depth + 1) for item in value[:MAX_ITEMS]]
    if isinstance(value, dict):
        return {
            str(key): _bounded_json(item, depth + 1)
            for key, item in list(value.items())[:MAX_ITEMS]
            if not _PRIVATE_KEY.search(str(key))
        }
    return None


def sanitize_chat_metadata(metadata: Any) -> Dict[str, Any]:
    """Return the durable allowlisted subset and reject an oversized result."""
    if not isinstance(metadata, dict):
        return {}

    safe = {
        key: _bounded_json(value)
        for key, value in metadata.items()
        if key in _TOP_LEVEL_KEYS and key not in {"sources", "debugPayloads"}
    }

    sources = metadata.get("sources")
    if isinstance(sources, list):
        safe["sources"] = [
            {
                key: (value[:500] if key == "text_preview" and isinstance(value, str) else _bounded_json(value))
                for key, value in source.items()
                if key in _SOURCE_KEYS
            }
            for source in sources[:MAX_ITEMS]
            if isinstance(source, dict)
        ]

    debug_payloads = metadata.get("debugPayloads")
    if isinstance(debug_payloads, dict):
        safe["debugPayloads"] = {
            key: _bounded_json(value)
            for key, value in debug_payloads.items()
            if key in _DEBUG_KEYS and not _PRIVATE_KEY.search(key)
        }

    encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError(f"chat metadata exceeds {MAX_METADATA_BYTES} bytes")
    return safe
