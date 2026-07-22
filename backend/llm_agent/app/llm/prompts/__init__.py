"""Prompt registry helpers package.

Re-exports all shared types and per-domain helpers so that
app.llm._prompt_registry_helpers can become a thin backward-compat shim.
"""
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
from app.llm.prompts import answer_generation, answer_evaluation, content_risk, query_rewrite, memory_extraction

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
    "answer_generation",
    "answer_evaluation",
    "content_risk",
    "query_rewrite",
    "memory_extraction",
]
