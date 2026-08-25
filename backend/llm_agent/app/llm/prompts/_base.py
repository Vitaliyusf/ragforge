"""Shared base types and JSON-extraction utilities for the prompts package.

All prompt modules import their base infrastructure from here.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel

from app.core.config import Settings
from app.schemas.llm import ModelExecutionRequest

PromptBuilder = Callable[[ModelExecutionRequest], "PromptRenderResult"]
# Parsers take the raw model output, and optionally the originating request
# when they declare ``parser_accepts_request``.
PromptParser = Callable[..., Any]
ModelResolver = Callable[[Settings], str]

STRUCTURED_OUTPUT_DEBUG_PREFIX = "__structured_output_debug__:"


@dataclass(frozen=True)
class PromptRenderResult:
    """Rendered prompt parts returned by prompt builders."""
    system_prompt: str
    raw_prompt: str


@dataclass(frozen=True)
class PromptRegistryEntry:
    """Registry metadata for one typed execution request version."""
    request_type: str
    prompt_version: str
    default_model: ModelResolver
    build_prompt: PromptBuilder
    parser: PromptParser
    output_model: Type[BaseModel]
    streaming_allowed: bool = False
    structured_output_required: bool = False
    # Parsers are called with the raw output only. A parser that must resolve
    # something back to the request (citation markers to passages) declares it
    # here rather than having the caller inspect its signature.
    parser_accepts_request: bool = False


@dataclass(frozen=True)
class StructuredExtractionResult:
    """Selected structured payload plus debug metadata about extraction."""
    payload: Any
    metadata: Dict[str, Any]


class StructuredOutputParseError(ValueError):
    """Structured-output parse failure carrying extraction metadata."""

    def __init__(self, message: str, metadata: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.metadata = metadata or {}


# ---------------------------------------------------------------------------
# Text formatting helpers
# ---------------------------------------------------------------------------

def _format_history(history: Optional[List[Any]]) -> str:
    if not history:
        return "None"
    return "\n".join(f"{message.role}: {message.content}" for message in history)


def _format_context(context: Any) -> str:
    if context is None:
        return "None"
    if isinstance(context, list):
        return "\n\n".join(_passage_text(item) for item in context)
    return str(context)


def _passage_text(item: Any) -> str:
    """Return the prose of one context item, whether string or ContextPassage."""
    text = getattr(item, "text", None)
    if text is not None:
        return str(text)
    if isinstance(item, dict) and "text" in item:
        return str(item["text"])
    return str(item)


def _context_passages(context: Any) -> List[Dict[str, Optional[str]]]:
    """Normalize a context input into an ordered list of citable passages.

    Index order is the citation contract: the passage at position ``i`` is what
    a ``[i + 1]`` marker in the answer refers to. A bare string or list of
    strings carries no ids, so ``source_id`` comes back None and a citation
    extracted against it can report only its marker.

    Returns:
        One dict per passage with ``source_id``, ``text`` and ``locator``.
    """
    if context is None:
        return []
    items = context if isinstance(context, list) else [context]
    passages: List[Dict[str, Optional[str]]] = []
    for item in items:
        if isinstance(item, dict):
            source_id = item.get("source_id")
            locator = item.get("locator")
        else:
            source_id = getattr(item, "source_id", None)
            locator = getattr(item, "locator", None)
        passages.append(
            {
                "source_id": None if source_id is None else str(source_id),
                "text": _passage_text(item),
                "locator": None if locator is None else str(locator),
            }
        )
    return passages


def _format_numbered_context(context: Any) -> str:
    """Render context as ``[n] text`` blocks so the model can cite by number.

    Numbering is 1-based and matches :func:`_context_passages` position for
    position; the two must stay in step or every extracted citation points at
    the wrong passage.
    """
    passages = _context_passages(context)
    if not passages:
        return "None"
    return "\n\n".join(
        f"[{index}] {passage['text']}"
        for index, passage in enumerate(passages, start=1)
    )


# ---------------------------------------------------------------------------
# JSON extraction utilities
# ---------------------------------------------------------------------------

def _extract_json_payload(raw_output: str) -> Any:
    candidate = raw_output.strip()
    if not candidate:
        raise ValueError("Model returned an empty response")

    if candidate.startswith("```"):
        fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", candidate, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            candidate = fence_match.group(1).strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(candidate[start : end + 1])

    start = candidate.find("[")
    end = candidate.rfind("]")
    if start != -1 and end != -1 and end > start:
        return json.loads(candidate[start : end + 1])

    raise ValueError("No valid JSON object found in model output")


def _scan_top_level_json_fragments(candidate: str) -> List[str]:
    fragments: List[str] = []
    start_index: Optional[int] = None
    stack: List[str] = []
    in_string = False
    escape = False

    pairs = {"{": "}", "[": "]"}
    closers = set(pairs.values())

    for index, char in enumerate(candidate):
        if in_string:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char in pairs:
            if not stack:
                start_index = index
            stack.append(pairs[char])
            continue

        if char in closers and stack:
            expected = stack.pop()
            if char != expected:
                stack.clear()
                start_index = None
                continue
            if not stack and start_index is not None:
                fragments.append(candidate[start_index : index + 1])
                start_index = None

    return fragments


def _extract_json_payload_with_metadata(
    raw_output: str, *, selection_policy: str = "last_valid"
) -> StructuredExtractionResult:
    candidate = raw_output.strip()
    if not candidate:
        raise StructuredOutputParseError(
            "Model returned an empty response",
            {"payload_count": 0, "selected_payload_index": None, "selection_policy": selection_policy, "extraction_mode": "empty"},
        )

    extraction_mode = "single_payload"
    selected_index = 0
    raw_candidates: List[str] = []
    parsed_candidates: List[Any] = []

    if candidate.startswith("```"):
        fence_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", candidate, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            candidate = fence_match.group(1).strip()

    try:
        parsed = json.loads(candidate)
        raw_candidates = [candidate]
        parsed_candidates = [parsed]
    except json.JSONDecodeError:
        raw_candidates = _scan_top_level_json_fragments(candidate)
        for fragment in raw_candidates:
            try:
                parsed_candidates.append(json.loads(fragment))
            except json.JSONDecodeError:
                continue

        if not parsed_candidates:
            metadata = {
                "payload_count": 0,
                "selected_payload_index": None,
                "selection_policy": selection_policy,
                "extraction_mode": "scan_failed" if raw_candidates else "no_complete_payload",
            }
            raise StructuredOutputParseError("No valid JSON object found in model output", metadata)

        if len(parsed_candidates) > 1:
            extraction_mode = "multi_payload_last_valid"
            selected_index = len(parsed_candidates) - 1 if selection_policy == "last_valid" else 0
        else:
            fragment = raw_candidates[0]
            extraction_mode = "single_payload" if fragment == candidate else "embedded_payload"
            selected_index = 0

    selected_payload = parsed_candidates[selected_index]
    metadata = {
        "payload_count": len(parsed_candidates),
        "selected_payload_index": selected_index,
        "selection_policy": selection_policy,
        "extraction_mode": extraction_mode,
        "candidates": parsed_candidates,
    }
    return StructuredExtractionResult(payload=selected_payload, metadata=metadata)


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

def _coerce_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return value


def _coerce_number(value: Any) -> Any:
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return value
        try:
            return float(normalized)
        except ValueError:
            return value
    return value


def _normalize_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("Expected a string or list of strings")


def _normalize_flag_item(item: Any) -> Dict[str, Optional[str]]:
    if isinstance(item, str):
        normalized = item.strip()
        if not normalized:
            raise ValueError("Risk flag strings must not be empty")
        return {"code": normalized, "span": None, "rationale": normalized}

    if not isinstance(item, dict):
        raise ValueError("Risk flags must be strings or objects")

    raw_code = item.get("code")
    raw_rationale = item.get("rationale", item.get("reason"))
    raw_span = item.get("span")

    code = str(raw_code or raw_rationale or "").strip()
    rationale = str(raw_rationale or raw_code or "").strip()
    span = None if raw_span is None else str(raw_span).strip() or None

    if not code or not rationale:
        raise ValueError("Risk flag objects must include a code or rationale")

    return {"code": code, "span": span, "rationale": rationale}


def _strip_prompt_echo(text: str) -> str:
    """Remove prompt echo that some models prepend before the actual answer."""
    # If the model echoed the prompt (which ends with "Answer:"), extract only what follows
    # the last occurrence so echoed content before the anchor is discarded.
    anchors = list(re.finditer(r'\bAnswer:\s*', text, flags=re.IGNORECASE))
    if anchors:
        candidate = text[anchors[-1].end():].strip()
        if candidate:
            text = candidate

    # Strip trailing conversation-turn echo (System:/User: continuation)
    match = re.search(r'\n+(?:System:|User:)', text)
    if match:
        text = text[:match.start()].strip()

    return re.sub(r'^Answer:\s*', '', text, flags=re.IGNORECASE).strip()
