"""Prompt builder and parser for the memory_extraction request type."""
from __future__ import annotations

import json
from typing import Any

from app.schemas.llm import MemoryExtractionRequest
from app.llm.prompts._base import PromptRenderResult, _extract_json_payload, _format_history


def build_prompt(request: MemoryExtractionRequest) -> PromptRenderResult:
    return PromptRenderResult(
        system_prompt=(
            "Extract stable user memory candidates from the conversation. "
            "Return JSON only. Avoid temporary or speculative details."
        ),
        raw_prompt=(
            f"Conversation History:\n{_format_history(request.input.conversation_history)}\n\n"
            f"Existing Memory:\n{json.dumps(request.input.existing_memory or [])}\n\n"
            f"Extraction Scope:\n{request.input.extraction_scope or 'user profile and stable preferences'}\n\n"
            "Return JSON with a top-level memories array. "
            "Each memory must include type, content, confidence, action."
        ),
    )


def parse(raw_output: str) -> Any:
    return _extract_json_payload(raw_output)
