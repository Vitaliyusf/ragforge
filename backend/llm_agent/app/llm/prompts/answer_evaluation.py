"""Prompt builders (v1 + v2) and parser for the answer_evaluation request type."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.schemas.llm import AnswerEvaluationRequest
from app.llm.prompts._base import (
    PromptRenderResult,
    StructuredExtractionResult,
    StructuredOutputParseError,
    _coerce_bool,
    _coerce_number,
    _extract_json_payload_with_metadata,
    _format_context,
    _format_numbered_context,
    _normalize_string_list,
)

# The judge's hallucination vocabulary. Anything else it invents is mapped to
# None rather than guessed at: an unrecognised verdict is an unmeasured turn,
# and treating it as "none" would quietly clear a possibly-hallucinated answer.
HALLUCINATION_VERDICTS = ("none", "minor", "severe")

_FALLBACK = {
    "verdict": "unavailable",
    "groundedness_score": None,
    "completeness_score": None,
    "safety_score": None,
    "issues": [],
    "claims": [],
    "unsupported_claim_count": None,
    "hallucination_verdict": None,
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

    claims = _normalize_claims(
        payload.get("claims")
        or payload.get("atomic_claims")
        or payload.get("claim_analysis")
    )
    normalized["claims"] = claims
    normalized["unsupported_claim_count"] = _normalize_unsupported_count(
        payload.get("unsupported_claim_count")
        if payload.get("unsupported_claim_count") is not None
        else payload.get("unsupported_claims"),
        claims,
    )
    normalized["hallucination_verdict"] = _normalize_hallucination_verdict(
        payload.get("hallucination_verdict")
        or payload.get("hallucination")
        or payload.get("hallucination_level")
    )

    return normalized


def _normalize_claims(value: Any) -> List[Dict[str, Any]]:
    """Coerce the judge's claim list into ``{claim, supported, ids}`` dicts.

    Defensive in the same spirit as the score coercions above: a claim that
    is unusable (no text) is dropped rather than raising, because one badly
    shaped entry must not cost the whole review its scores.

    A claim whose ``supported`` flag is missing or non-boolean is treated as
    unsupported: the judge is asserting support, and an absent assertion is
    not support.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        return []

    claims: List[Dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                claims.append(
                    {"claim": text, "supported": False, "supporting_passage_ids": []}
                )
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("claim") or item.get("text") or item.get("statement") or "").strip()
        if not text:
            continue
        supported = _coerce_bool(
            item.get("supported")
            if item.get("supported") is not None
            else item.get("is_supported")
        )
        raw_ids = (
            item.get("supporting_passage_ids")
            if item.get("supporting_passage_ids") is not None
            else item.get("supporting_passages")
            if item.get("supporting_passages") is not None
            else item.get("passage_ids")
        )
        try:
            passage_ids = _normalize_string_list(raw_ids)
        except ValueError:
            passage_ids = []
        claims.append(
            {
                "claim": text,
                "supported": supported is True,
                "supporting_passage_ids": passage_ids,
            }
        )
    return claims


def _normalize_unsupported_count(
    value: Any,
    claims: List[Dict[str, Any]],
) -> Optional[int]:
    """Return the unsupported-claim count, preferring the claim list itself.

    The judge often reports a count that disagrees with the claims it just
    listed. The list is the auditable artefact, so it wins whenever it is
    non-empty; the reported number is only used when no claims came back.
    """
    if claims:
        return sum(1 for claim in claims if not claim.get("supported"))
    if value is None:
        return None
    try:
        count = int(_coerce_number(value))
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


def _normalize_hallucination_verdict(value: Any) -> Optional[str]:
    """Map the judge's hallucination verdict onto the known vocabulary."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in HALLUCINATION_VERDICTS:
        return normalized
    # A few spellings seen from smaller models, mapped rather than discarded.
    aliases = {
        "no": "none",
        "false": "none",
        "not_hallucinated": "none",
        "low": "minor",
        "moderate": "minor",
        "medium": "minor",
        "major": "severe",
        "high": "severe",
        "critical": "severe",
    }
    return aliases.get(normalized)


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
            f"Reference Context:\n{_format_numbered_context(request.input.reference_context)}\n\n"
            f"Rubric:\n{json.dumps(rubric)}\n\n"
            "Split the answer into atomic claims. For each, decide whether the\n"
            "reference context above supports it, and list the passage numbers\n"
            "that do. A claim no passage supports is unsupported.\n\n"
            "Return exactly one JSON object with these keys and value types:\n"
            '- "verdict": string\n- "groundedness_score": number\n'
            '- "completeness_score": number\n- "safety_score": number\n'
            '- "issues": array of strings\n'
            '- "claims": array of {"claim": string, "supported": boolean, '
            '"supporting_passage_ids": array of strings}\n'
            '- "unsupported_claim_count": number\n'
            '- "hallucination_verdict": one of "none", "minor", "severe"\n'
            '- "revision_applied": boolean\n\n'
            "Use \"none\" when every claim is supported, \"minor\" for an unsupported\n"
            "detail that does not change the answer, and \"severe\" for an unsupported\n"
            "claim a reader would act on.\n"
            "Do not include markdown, explanations, trailing text, extra keys, or alternative JSON objects.\n"
            "If you revise your answer internally, output only the final JSON object once.\n"
            "Minimal valid example:\n"
            '{"verdict":"pass","groundedness_score":0.92,"completeness_score":0.85,'
            '"safety_score":1.0,"issues":[],"claims":[{"claim":"X is Y",'
            '"supported":true,"supporting_passage_ids":["1"]}],'
            '"unsupported_claim_count":0,"hallucination_verdict":"none",'
            '"revision_applied":false}'
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
