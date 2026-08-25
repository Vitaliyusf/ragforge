"""Prompt registry and output parsing for typed model execution.

Re-exports all data types and helper functions from the helpers module,
and defines the PromptRegistry lookup class.
"""
from __future__ import annotations

from typing import Dict, Optional

from app.core.config import Settings
from app.schemas.llm import (
    AnswerReviewParsedOutput,
    AnswerGenerationParsedOutput,
    ContentRiskScanParsedOutput,
    MemoryExtractionParsedOutput,
    QueryRewriteParsedOutput,
)
from app.llm._prompt_registry_helpers import (
    STRUCTURED_OUTPUT_DEBUG_PREFIX,
    PromptBuilder,
    PromptParser,
    ModelResolver,
    PromptRenderResult,
    PromptRegistryEntry,
    StructuredExtractionResult,
    StructuredOutputParseError,
    _build_answer_evaluation_prompt_v1,
    _build_answer_evaluation_prompt_v2,
    _build_answer_generation_prompt,
    _build_content_risk_scan_prompt_v1,
    _build_content_risk_scan_prompt_v2,
    _build_memory_extraction_prompt,
    _build_query_rewrite_prompt,
    _extract_json_payload,
    _extract_json_payload_with_metadata,
    _parse_answer_evaluation,
    _parse_answer_generation,
    _parse_content_risk_scan,
    _parse_memory_extraction,
    _parse_query_rewrite,
)

__all__ = [
    "STRUCTURED_OUTPUT_DEBUG_PREFIX",
    "PromptBuilder",
    "PromptParser",
    "ModelResolver",
    "PromptRenderResult",
    "PromptRegistryEntry",
    "StructuredExtractionResult",
    "StructuredOutputParseError",
    "PromptRegistry",
    "_extract_json_payload",
    "_extract_json_payload_with_metadata",
]


class PromptRegistry:
    """Resolve prompt builders, parsers, and defaults for typed execution."""

    def __init__(self, config: Settings):
        self.config = config
        self._default_versions: Dict[str, str] = {
            "answer_generation": "answer_generation.v1",
            "answer_evaluation": "answer_evaluation.v2",
            "content_risk_scan": "content_risk_scan.v2",
            "query_rewrite": "query_rewrite.v1",
            "memory_extraction": "memory_extraction.v1",
        }
        self._entries: Dict[str, Dict[str, PromptRegistryEntry]] = {
            "answer_generation": {
                "answer_generation.v1": PromptRegistryEntry(
                    request_type="answer_generation",
                    prompt_version="answer_generation.v1",
                    default_model=lambda settings: settings.rag_chat_model or settings.default_model or "",
                    build_prompt=_build_answer_generation_prompt,
                    parser=_parse_answer_generation,
                    output_model=AnswerGenerationParsedOutput,
                    streaming_allowed=True,
                    structured_output_required=False,
                    parser_accepts_request=True,
                )
            },
            "answer_evaluation": {
                "answer_evaluation.v2": PromptRegistryEntry(
                    request_type="answer_evaluation",
                    prompt_version="answer_evaluation.v2",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=_build_answer_evaluation_prompt_v2,
                    parser=_parse_answer_evaluation,
                    output_model=AnswerReviewParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=True,
                ),
                "answer_evaluation.v1": PromptRegistryEntry(
                    request_type="answer_evaluation",
                    prompt_version="answer_evaluation.v1",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=_build_answer_evaluation_prompt_v1,
                    parser=_parse_answer_evaluation,
                    output_model=AnswerReviewParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=True,
                )
            },
            "content_risk_scan": {
                "content_risk_scan.v2": PromptRegistryEntry(
                    request_type="content_risk_scan",
                    prompt_version="content_risk_scan.v2",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=_build_content_risk_scan_prompt_v2,
                    parser=_parse_content_risk_scan,
                    output_model=ContentRiskScanParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=True,
                ),
                "content_risk_scan.v1": PromptRegistryEntry(
                    request_type="content_risk_scan",
                    prompt_version="content_risk_scan.v1",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=_build_content_risk_scan_prompt_v1,
                    parser=_parse_content_risk_scan,
                    output_model=ContentRiskScanParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=True,
                )
            },
            "query_rewrite": {
                "query_rewrite.v1": PromptRegistryEntry(
                    request_type="query_rewrite",
                    prompt_version="query_rewrite.v1",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=_build_query_rewrite_prompt,
                    parser=_parse_query_rewrite,
                    output_model=QueryRewriteParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=False,
                )
            },
            "memory_extraction": {
                "memory_extraction.v1": PromptRegistryEntry(
                    request_type="memory_extraction",
                    prompt_version="memory_extraction.v1",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=_build_memory_extraction_prompt,
                    parser=_parse_memory_extraction,
                    output_model=MemoryExtractionParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=False,
                )
            },
        }

    def resolve(self, request_type: str, prompt_version: Optional[str]) -> PromptRegistryEntry:
        """Resolve the prompt registry entry for a request type and version."""
        versions = self._entries.get(request_type)
        if not versions:
            raise ValueError(f"Unsupported request_type: {request_type}")

        if prompt_version:
            entry = versions.get(prompt_version)
            if not entry:
                raise ValueError(f"Unsupported prompt_version '{prompt_version}' for {request_type}")
            return entry

        return versions[self._default_versions[request_type]]
