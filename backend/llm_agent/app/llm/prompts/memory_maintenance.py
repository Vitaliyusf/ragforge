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


def build_memory_curation_prompt_v1(request: MemoryCurationRequest) -> PromptRenderResult:
    """Render the historical v1 prompt for explicit replay only."""
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


def build_memory_curation_prompt_v2(request: MemoryCurationRequest) -> PromptRenderResult:
    correction = ""
    if request.input.validation_feedback:
        correction = (
            "\n\nThe prior response failed deterministic validation: "
            f"{request.input.validation_feedback}\nReturn a corrected full plan."
        )
    return PromptRenderResult(
        system_prompt=(
            "You are a bounded memory policy, not a persistence owner. Retain only durable facts "
            "explicitly supplied by the user or an approved product source. Ignore greetings, "
            "transient chatter, assistant-authored claims, unsupported inferences, and duplicates. "
            "Distinguish corrections, temporal updates, scope differences, paraphrases, and unrelated "
            "facts. Never invent an id or authorization scope. Return JSON only."
        ),
        raw_prompt=(
            f"Conversation:\n{_format_history(request.input.conversation_history)}\n\n"
            f"Existing memory:\n{json.dumps(request.input.existing_memory, ensure_ascii=False)}\n\n"
            "Return an actions array (maximum 10) and a one-line summary. Allowed actions are "
            "ignore, create, update, supersede, merge_suggestion, and delete. Create requires content "
            "and no memory_id. Update/supersede require content and an id from Existing memory. "
            "Merge suggestions require an existing id and are advisory only. Delete requires an "
            f"existing id and is {'authorized' if request.input.deletion_authorized else 'NOT authorized'} "
            "for this request. Prefer ignore whenever evidence or lifecycle intent is uncertain. "
            "Optional fields are category, confidence (0..1), reason, fact_key, and scope."
            f"{correction}"
        ),
    )


# Current builder name retained for direct callers; registry versions use the
# explicit functions above so old prompt provenance stays replayable.
build_memory_curation_prompt = build_memory_curation_prompt_v2


def parse(raw_output: str) -> Any:
    return _extract_json_payload(raw_output)
