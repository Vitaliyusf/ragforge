"""Prompt builders for Memory-owned title, summary, and curation requests."""
from __future__ import annotations

import json
from typing import Any

from app.llm.prompts._base import PromptRenderResult, _extract_json_payload, _format_history
from app.schemas.llm import ChatSummaryRequest, ChatTitleRequest, MemoryCurationRequest


def build_chat_title_prompt(request: ChatTitleRequest) -> PromptRenderResult:
    return PromptRenderResult(
        system_prompt="Create a concise conversation title. Return JSON only.",
        raw_prompt=(
            f"Conversation:\n{_format_history(request.input.conversation_history[:10])}\n\n"
            'Return exactly one JSON object: {"title":"maximum 50 characters"}.'
        ),
    )


def build_chat_summary_prompt(request: ChatSummaryRequest) -> PromptRenderResult:
    return PromptRenderResult(
        system_prompt=(
            "Compress the conversation into at most five concise sentences. "
            "Keep key facts, decisions, and outcomes; omit pleasantries. Return JSON only."
        ),
        raw_prompt=(
            f"Conversation:\n{_format_history(request.input.conversation_history)}\n\n"
            'Return exactly one JSON object: {"summary":"compressed history"}.'
        ),
    )


def build_memory_curation_prompt(request: MemoryCurationRequest) -> PromptRenderResult:
    return PromptRenderResult(
        system_prompt=(
            "Maintain concise, durable user memory. Merge duplicates, remove superseded facts, "
            "and add at most three genuinely new insights. Return JSON only."
        ),
        raw_prompt=(
            f"Conversation:\n{_format_history(request.input.conversation_history)}\n\n"
            f"Existing memory:\n{json.dumps(request.input.existing_memory, ensure_ascii=False)}\n\n"
            "Return an actions array (maximum 10) and a one-line summary. "
            "Each action is add, update, or delete. Add requires content and optional category; "
            "update requires memory_id and content; delete requires memory_id."
        ),
    )


def parse(raw_output: str) -> Any:
    return _extract_json_payload(raw_output)
