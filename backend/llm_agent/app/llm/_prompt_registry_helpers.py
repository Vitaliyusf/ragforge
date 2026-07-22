"""Backward-compatibility re-export for prompt registry helpers.

All types and helpers now live in app.llm.prompts.*
Import from there in new code.
"""
# noqa: F401
from app.llm.prompts._base import (
    STRUCTURED_OUTPUT_DEBUG_PREFIX,
    ModelResolver,
    PromptBuilder,
    PromptParser,
    PromptRegistryEntry,
    PromptRenderResult,
    StructuredExtractionResult,
    StructuredOutputParseError,
    _extract_json_payload,
    _extract_json_payload_with_metadata,
)
from app.llm.prompts.answer_generation import build_prompt as _build_answer_generation_prompt
from app.llm.prompts.answer_generation import parse as _parse_answer_generation
from app.llm.prompts.answer_evaluation import build_prompt_v1 as _build_answer_evaluation_prompt_v1
from app.llm.prompts.answer_evaluation import build_prompt_v2 as _build_answer_evaluation_prompt_v2
from app.llm.prompts.answer_evaluation import parse as _parse_answer_evaluation
from app.llm.prompts.content_risk import build_prompt_v1 as _build_content_risk_scan_prompt_v1
from app.llm.prompts.content_risk import build_prompt_v2 as _build_content_risk_scan_prompt_v2
from app.llm.prompts.content_risk import parse as _parse_content_risk_scan
from app.llm.prompts.query_rewrite import build_prompt as _build_query_rewrite_prompt
from app.llm.prompts.query_rewrite import parse as _parse_query_rewrite
from app.llm.prompts.memory_extraction import build_prompt as _build_memory_extraction_prompt
from app.llm.prompts.memory_extraction import parse as _parse_memory_extraction

__all__ = [
    "STRUCTURED_OUTPUT_DEBUG_PREFIX",
    "ModelResolver",
    "PromptBuilder",
    "PromptParser",
    "PromptRegistryEntry",
    "PromptRenderResult",
    "StructuredExtractionResult",
    "StructuredOutputParseError",
    "_extract_json_payload",
    "_extract_json_payload_with_metadata",
    "_build_answer_generation_prompt",
    "_parse_answer_generation",
    "_build_answer_evaluation_prompt_v1",
    "_build_answer_evaluation_prompt_v2",
    "_parse_answer_evaluation",
    "_build_content_risk_scan_prompt_v1",
    "_build_content_risk_scan_prompt_v2",
    "_parse_content_risk_scan",
    "_build_query_rewrite_prompt",
    "_parse_query_rewrite",
    "_build_memory_extraction_prompt",
    "_parse_memory_extraction",
]
