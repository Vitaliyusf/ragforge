"""Prompt builder and parser for the answer_generation request type."""
from __future__ import annotations

from typing import Any, Dict

from app.schemas.llm import AnswerGenerationRequest
from app.llm.prompts._base import PromptRenderResult, _format_context, _format_history, _strip_prompt_echo


def build_prompt(request: AnswerGenerationRequest) -> PromptRenderResult:
    instructions = request.input.instructions or (
        "Answer briefly and professionally in at most 1-3 short sentences, using the "
        "supplied context when relevant. No filler, no preamble."
    )
    return PromptRenderResult(
        system_prompt=(
            "You are a professional assistant. Answer briefly and professionally in at "
            "most 1-3 short sentences. No filler, no preamble, no hidden reasoning. "
            "If the context is insufficient, say so plainly."
        ),
        raw_prompt=(
            f"Instructions:\n{instructions}\n\n"
            f"Conversation History:\n{_format_history(request.input.conversation_history)}\n\n"
            f"Retrieved Context:\n{_format_context(request.input.retrieved_context)}\n\n"
            f"Question:\n{request.input.question}\n\n"
            "Do not repeat these instructions. Write only the answer below.\n"
            "Answer:"
        ),
    )


def parse(raw_output: str) -> Dict[str, Any]:
    text = _strip_prompt_echo(raw_output.strip())
    return {
        "answer": text,
        "citations": None,
        "confidence": None,
    }
