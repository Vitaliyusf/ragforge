"""Prompt builder and parser for the query_rewrite request type."""
from __future__ import annotations

from typing import Any

from app.schemas.llm import QueryRewriteRequest
from app.llm.prompts._base import PromptRenderResult, _extract_json_payload, _format_history


def build_prompt(request: QueryRewriteRequest) -> PromptRenderResult:
    return PromptRenderResult(
        system_prompt=(
            "You rewrite user queries for retrieval and search. "
            "Prefer a single best rewritten query and keep the meaning intact."
        ),
        raw_prompt=(
            f"Conversation History:\n{_format_history(request.input.conversation_history)}\n\n"
            f"Rewrite Goal:\n{request.input.rewrite_goal or 'Improve retrieval quality'}\n\n"
            f"Original Query:\n{request.input.query}\n\n"
            "Return JSON with keys: rewritten_query, search_intent."
        ),
    )


def parse(raw_output: str) -> Any:
    try:
        return _extract_json_payload(raw_output)
    except ValueError:
        return {
            "rewritten_query": raw_output.strip(),
            "search_intent": None,
        }
