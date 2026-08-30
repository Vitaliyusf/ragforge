"""Prompt registry for typed model execution."""
from __future__ import annotations

from typing import Dict, Optional

from app.core.config import Settings
from app.llm.prompts import (
    answer_evaluation,
    answer_generation,
    content_risk,
    memory_extraction,
    memory_maintenance,
    query_rewrite,
)
from app.llm.prompts._base import (
    STRUCTURED_OUTPUT_DEBUG_PREFIX,
    ModelResolver,
    PromptBuilder,
    PromptParser,
    PromptRenderResult,
    PromptRegistryEntry,
    StructuredExtractionResult,
    StructuredOutputParseError,
    _extract_json_payload,
    _extract_json_payload_with_metadata,
)
from app.schemas.llm import (
    AnswerGenerationParsedOutput,
    AnswerReviewParsedOutput,
    ChatSummaryParsedOutput,
    ChatTitleParsedOutput,
    ContentRiskScanParsedOutput,
    MemoryCurationParsedOutput,
    MemoryCurationParsedOutputV1,
    MemoryExtractionParsedOutput,
    QueryRewriteParsedOutput,
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
            "chat_title": "chat_title.v1",
            "chat_summary": "chat_summary.v1",
            "memory_curation": "memory_curation.v2",
        }
        self._entries: Dict[str, Dict[str, PromptRegistryEntry]] = {
            "answer_generation": {
                "answer_generation.v1": PromptRegistryEntry(
                    request_type="answer_generation",
                    prompt_version="answer_generation.v1",
                    default_model=lambda settings: settings.rag_chat_model or settings.default_model or "",
                    build_prompt=answer_generation.build_prompt,
                    parser=answer_generation.parse,
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
                    build_prompt=answer_evaluation.build_prompt_v2,
                    parser=answer_evaluation.parse,
                    output_model=AnswerReviewParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=True,
                ),
                "answer_evaluation.v1": PromptRegistryEntry(
                    request_type="answer_evaluation",
                    prompt_version="answer_evaluation.v1",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=answer_evaluation.build_prompt_v1,
                    parser=answer_evaluation.parse,
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
                    build_prompt=content_risk.build_prompt_v2,
                    parser=content_risk.parse,
                    output_model=ContentRiskScanParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=True,
                ),
                "content_risk_scan.v1": PromptRegistryEntry(
                    request_type="content_risk_scan",
                    prompt_version="content_risk_scan.v1",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=content_risk.build_prompt_v1,
                    parser=content_risk.parse,
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
                    build_prompt=query_rewrite.build_prompt,
                    parser=query_rewrite.parse,
                    output_model=QueryRewriteParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=True,
                )
            },
            "memory_extraction": {
                "memory_extraction.v1": PromptRegistryEntry(
                    request_type="memory_extraction",
                    prompt_version="memory_extraction.v1",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=memory_extraction.build_prompt,
                    parser=memory_extraction.parse,
                    output_model=MemoryExtractionParsedOutput,
                    streaming_allowed=False,
                    structured_output_required=True,
                )
            },
            "chat_title": {
                "chat_title.v1": PromptRegistryEntry(
                    request_type="chat_title",
                    prompt_version="chat_title.v1",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=memory_maintenance.build_chat_title_prompt,
                    parser=memory_maintenance.parse,
                    output_model=ChatTitleParsedOutput,
                    structured_output_required=True,
                )
            },
            "chat_summary": {
                "chat_summary.v1": PromptRegistryEntry(
                    request_type="chat_summary",
                    prompt_version="chat_summary.v1",
                    default_model=lambda settings: settings.summary_model or settings.default_model or "",
                    build_prompt=memory_maintenance.build_chat_summary_prompt,
                    parser=memory_maintenance.parse,
                    output_model=ChatSummaryParsedOutput,
                    structured_output_required=True,
                )
            },
            "memory_curation": {
                "memory_curation.v2": PromptRegistryEntry(
                    request_type="memory_curation",
                    prompt_version="memory_curation.v2",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=memory_maintenance.build_memory_curation_prompt_v2,
                    parser=memory_maintenance.parse,
                    output_model=MemoryCurationParsedOutput,
                    structured_output_required=True,
                ),
                "memory_curation.v1": PromptRegistryEntry(
                    request_type="memory_curation",
                    prompt_version="memory_curation.v1",
                    default_model=lambda settings: settings.default_model or settings.rag_chat_model or "",
                    build_prompt=memory_maintenance.build_memory_curation_prompt_v1,
                    parser=memory_maintenance.parse,
                    output_model=MemoryCurationParsedOutputV1,
                    structured_output_required=True,
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
