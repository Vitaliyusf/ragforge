"""Prompt builder and parser for the answer_generation request type.

Citation policy, stated once here because every downstream metric depends on
it:

* The prompt numbers the retrieved passages ``[1]``, ``[2]``, ... and asks the
  model to cite them inline.
* **Markers are preserved in the displayed answer text.** They are not
  stripped. Answer tokens stream to the chat UI as they are produced, so
  removing markers at parse time would leave the final message differing from
  what the reader just watched appear. The frontend therefore renders ``[1]``
  as part of the answer.
* ``citations`` is ``[]`` when the feature is on and the model cited nothing,
  and ``None`` when citation extraction did not run at all (the feature is
  off, or the parser was called without the originating request and so has no
  passage list to resolve markers against). Those two states are different
  facts and downstream aggregation must not conflate them.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.config import Settings, get_settings
from app.schemas.llm import AnswerGenerationRequest
from app.llm.prompts._base import (
    PromptRenderResult,
    _context_passages,
    _format_context,
    _format_history,
    _format_numbered_context,
    _strip_prompt_echo,
)

# Bounded digit run: an unbounded \d+ would let a runaway "[999999999]" become
# a marker, and three digits is already far past any realistic top_k.
_CITATION_MARKER = re.compile(r"\[(\d{1,3})\]")

# Kept deliberately short. The 1-3 sentence constraint is the point of this
# prompt; asking for citations must not turn it into a verbose-answer change.
_CITATION_INSTRUCTION = (
    "Cite the passages that support your answer inline, as [1], [2], matching "
    "the numbers above. Cite only numbers that exist. Still answer in at most "
    "1-3 short sentences."
)

_SNIPPET_MAX_CHARS = 240


def _citations_enabled(settings: Optional[Settings] = None) -> bool:
    """Return whether answers should ask for and carry citations.

    Falls back to enabled when settings cannot be loaded: the flag exists to
    let an operator turn the feature off deliberately, not to have it silently
    disabled by an unrelated configuration failure.
    """
    try:
        resolved = settings if settings is not None else get_settings()
    except Exception:  # pragma: no cover - depends on environment
        return True
    return bool(getattr(resolved, "enable_answer_citations", True))


def build_prompt(request: AnswerGenerationRequest) -> PromptRenderResult:
    citations_on = _citations_enabled()
    instructions = request.input.instructions or (
        "Answer briefly and professionally in at most 1-3 short sentences, using the "
        "supplied context when relevant. No filler, no preamble."
    )
    context = (
        _format_numbered_context(request.input.retrieved_context)
        if citations_on
        else _format_context(request.input.retrieved_context)
    )
    citation_block = f"{_CITATION_INSTRUCTION}\n\n" if citations_on else ""
    return PromptRenderResult(
        system_prompt=(
            "You are a professional assistant. Answer briefly and professionally in at "
            "most 1-3 short sentences. No filler, no preamble, no hidden reasoning. "
            "If the context is insufficient, say so plainly."
        ),
        raw_prompt=(
            f"Instructions:\n{instructions}\n\n"
            f"Conversation History:\n{_format_history(request.input.conversation_history)}\n\n"
            f"Retrieved Context:\n{context}\n\n"
            f"Question:\n{request.input.question}\n\n"
            f"{citation_block}"
            "Do not repeat these instructions. Write only the answer below.\n"
            "Answer:"
        ),
    )


def extract_citations(
    answer: str,
    passages: List[Dict[str, Optional[str]]],
) -> Dict[str, Any]:
    """Resolve ``[n]`` markers in an answer against the numbered passages.

    Markers are de-duplicated on first appearance, so an answer citing ``[2]``
    three times yields one citation. A marker outside ``1..len(passages)`` is
    discarded rather than clamped: clamping a bad marker onto a real passage
    would turn a hallucinated citation into a correct-looking one and inflate
    every citation-precision figure computed from this output.

    Args:
        answer: The answer text, markers still in place.
        passages: Passages in prompt order, as built by ``_context_passages``.

    Returns:
        ``citations`` (ordered, de-duplicated) and ``invalid_citation_count``
        (markers pointing outside the passage range, including repeats of the
        same bad marker only once).
    """
    seen: List[int] = []
    invalid: List[int] = []
    for match in _CITATION_MARKER.finditer(answer):
        index = int(match.group(1))
        if 1 <= index <= len(passages):
            if index not in seen:
                seen.append(index)
        elif index not in invalid:
            invalid.append(index)

    citations: List[Dict[str, Optional[str]]] = []
    for index in seen:
        passage = passages[index - 1]
        text = passage.get("text") or ""
        citations.append(
            {
                "source_id": passage.get("source_id"),
                "locator": passage.get("locator") or f"[{index}]",
                "snippet": text[:_SNIPPET_MAX_CHARS] or None,
            }
        )
    return {"citations": citations, "invalid_citation_count": len(invalid)}


def parse(
    raw_output: str,
    request: Optional[AnswerGenerationRequest] = None,
) -> Dict[str, Any]:
    """Parse a generated answer, extracting inline citation markers.

    Markers are left in ``answer`` — see this module's docstring for why.

    Args:
        raw_output: The model's raw text output.
        request: The originating request, needed to map a marker back to the
            passage it refers to. Without it no mapping is possible and
            ``citations`` is None rather than a guess.
    """
    text = _strip_prompt_echo(raw_output.strip())
    if request is None or not _citations_enabled():
        return {"answer": text, "citations": None, "confidence": None}

    passages = _context_passages(request.input.retrieved_context)
    extracted = extract_citations(text, passages)
    return {
        "answer": text,
        "citations": extracted["citations"],
        "invalid_citation_count": extracted["invalid_citation_count"],
        "confidence": None,
    }
