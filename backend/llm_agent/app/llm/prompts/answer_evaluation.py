"""Prompt builders (v1 + v2) and parser for the answer_evaluation request type."""
from __future__ import annotations

import json
from typing import Any

from app.schemas.llm import AnswerEvaluationRequest
from app.llm.prompts._base import (
    PromptRenderResult,
    StructuredExtractionResult,
    StructuredOutputParseError,
    _coerce_bool,
    _coerce_number,
    _extract_json_payload_with_metadata,
    _format_context,
    _normalize_string_list,
)

_FALLBACK = {
    "verdict": "unavailable",
    "groundedness_score": None,
    "completeness_score": None,
    "safety_score": None,
    "issues": [],
    "revision_applied": False,
}


def _normalize_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        raise ValueError("Answer evaluation output must be a JSON object")

    normalized = dict(payload)
    normalized["issues"] = _normalize_string_list(payload.get("issues"))

    groundedness = (
        payload.get("groundedness_score")
        or payload.get("grounding_score")
        or payload.get("groundedness")
        or payload.get("relevance_score")
    )
    completeness = (
        payload.get("completeness_score")
        or payload.get("completeness")
        or payload.get("coverage_score")
    )
    safety = (
        payload.get("safety_score")
        or payload.get("safety")
        or payload.get("harmlessness_score")
    )

    normalized["groundedness_score"] = _coerce_number(groundedness)
    normalized["completeness_score"] = _coerce_number(completeness)
    normalized["safety_score"] = _coerce_number(safety)
    normalized["revision_applied"] = _coerce_bool(payload.get("revision_applied", False))

    verdict = payload.get("verdict") or payload.get("result") or payload.get("assessment")
    if verdict is not None:
        normalized["verdict"] = str(verdict).strip()

    return normalized


def build_prompt_v1(request: AnswerEvaluationRequest) -> PromptRenderResult:
    rubric = request.input.rubric or ["accuracy", "grounding", "completeness", "clarity"]
    return PromptRenderResult(
        system_prompt=(
            "You evaluate answer quality. Respond with JSON only. "
            "No markdown, no code fences, no additional commentary."
        ),
        raw_prompt=(
            "Review the answer against the question and reference context.\n\n"
            f"Question:\n{request.input.question}\n\n"
            f"Answer:\n{request.input.answer}\n\n"
            f"Reference Context:\n{_format_context(request.input.reference_context)}\n\n"
            f"Rubric:\n{json.dumps(rubric)}\n\n"
            "Return a JSON object with exactly these keys:\n"
            "- verdict\n- groundedness_score\n- completeness_score\n"
            "- safety_score\n- issues\n- revision_applied\n\n"
            "issues must be an array of short strings. "
            "Do not include review_id, model_name, created_at, markdown, or extra keys."
        ),
    )


def build_prompt_v2(request: AnswerEvaluationRequest) -> PromptRenderResult:
    rubric = request.input.rubric or ["accuracy", "grounding", "completeness", "clarity"]
    return PromptRenderResult(
        system_prompt=(
            "You evaluate answer quality. Return exactly one JSON object and nothing else. "
            "Do not wrap the JSON in markdown or code fences."
        ),
        raw_prompt=(
            "Review the answer against the question and reference context.\n\n"
            f"Question:\n{request.input.question}\n\n"
            f"Answer:\n{request.input.answer}\n\n"
            f"Reference Context:\n{_format_context(request.input.reference_context)}\n\n"
            f"Rubric:\n{json.dumps(rubric)}\n\n"
            "Return exactly one JSON object with these keys and value types:\n"
            '- "verdict": string\n- "groundedness_score": number\n'
            '- "completeness_score": number\n- "safety_score": number\n'
            '- "issues": array of strings\n- "revision_applied": boolean\n\n'
            "Do not include markdown, explanations, trailing text, extra keys, or alternative JSON objects.\n"
            "If you revise your answer internally, output only the final JSON object once.\n"
            "Minimal valid example:\n"
            '{"verdict":"pass","groundedness_score":0.92,"completeness_score":0.85,'
            '"safety_score":1.0,"issues":[],"revision_applied":false}'
        ),
    )


def parse(raw_output: str) -> Any:
    try:
        extracted = _extract_json_payload_with_metadata(raw_output, selection_policy="last_valid")
        return StructuredExtractionResult(
            payload=_normalize_payload(extracted.payload),
            metadata=extracted.metadata,
        )
    except (StructuredOutputParseError, ValueError):
        fallback_metadata = {
            "extraction_mode": "prose_fallback",
            "payload_count": 0,
            "selected_payload_index": None,
        }
        return StructuredExtractionResult(payload=dict(_FALLBACK), metadata=fallback_metadata)
