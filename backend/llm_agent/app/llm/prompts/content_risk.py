"""Prompt builders (v1 + v2) and parser for the content_risk_scan request type."""
from __future__ import annotations

import json
from typing import Any

from app.schemas.llm import ContentRiskScanRequest
from app.llm.prompts._base import (
    PromptRenderResult,
    StructuredExtractionResult,
    _extract_json_payload_with_metadata,
    _normalize_flag_item,
    _normalize_string_list,
)


def _normalize_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        raise ValueError("Content risk scan output must be a JSON object")

    normalized = dict(payload)
    normalized["categories"] = _normalize_string_list(payload.get("categories"))
    flags = payload.get("flags") or []
    if isinstance(flags, str):
        flags = [flags]
    if not isinstance(flags, list):
        raise ValueError("Risk scan flags must be a string or list")
    normalized["flags"] = [_normalize_flag_item(flag) for flag in flags]
    return normalized


def build_prompt_v1(request: ContentRiskScanRequest) -> PromptRenderResult:
    policy_hints = request.input.policy_hints or []
    return PromptRenderResult(
        system_prompt=(
            "You perform content risk classification. Respond with JSON only. "
            "No markdown, no code fences, no extra prose."
        ),
        raw_prompt=(
            f"Content Type: {request.input.content_type or 'unknown'}\n"
            f"Policy Hints: {json.dumps(policy_hints)}\n\n"
            f"Content:\n{request.input.content}\n\n"
            "Return a JSON object with keys: risk_level, categories, flags, summary.\n"
            "flags must be an array of objects with keys: code, span, rationale."
        ),
    )


def build_prompt_v2(request: ContentRiskScanRequest) -> PromptRenderResult:
    policy_hints = request.input.policy_hints or []
    return PromptRenderResult(
        system_prompt=(
            "You perform content risk classification. Return exactly one JSON object and nothing else. "
            "Do not use markdown, code fences, or commentary."
        ),
        raw_prompt=(
            f"Content Type: {request.input.content_type or 'unknown'}\n"
            f"Policy Hints: {json.dumps(policy_hints)}\n\n"
            f"Content:\n{request.input.content}\n\n"
            "Return exactly one JSON object with these keys and value types:\n"
            '- "risk_level": string\n'
            '- "categories": array of strings\n'
            '- "flags": array of objects with keys "code" (string), "span" (string or null), "rationale" (string)\n'
            '- "summary": string\n\n'
            "Do not include extra keys, markdown, surrounding prose, or alternative JSON objects.\n"
            "If you revise your answer internally, output only the final JSON object once.\n"
            "Minimal valid example:\n"
            '{"risk_level":"low","categories":["none"],"flags":[],"summary":"No material policy issues detected."}'
        ),
    )


def parse(raw_output: str) -> Any:
    extracted = _extract_json_payload_with_metadata(raw_output, selection_policy="last_valid")
    return StructuredExtractionResult(
        payload=_normalize_payload(extracted.payload),
        metadata=extracted.metadata,
    )
