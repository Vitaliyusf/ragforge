"""Context-window budgeting and boundary-aware text splitting.

Shared by the summary and metadata services. Both used to cap input by a flat
character count (``max_text_length``), which is unrelated to the model's real
token window — a 50k-character cap against a 6144-token vLLM window overflows
the server and fails the request. This module sizes input in tokens against the
window the server actually reports, and splits anything larger into as few
overlapping pieces as will fit.
"""
from __future__ import annotations

from typing import Any, List, Optional

# Conservative characters-per-token ratio. Real English text runs ~4 chars per
# token; deliberately under-estimating here means the budget errs on the side of
# a prompt that is too small rather than one the server rejects.
DEFAULT_CHARS_PER_TOKEN = 3.5

# Headroom for chat/template tokens the provider adds around our prompt, plus
# ordinary tokenizer variance.
SAFETY_MARGIN_TOKENS = 128

# Never hand the model a budget so small that splitting makes no progress.
MIN_BUDGET_CHARS = 256


def estimate_tokens(text: str, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
    """Estimate the token count of ``text``, rounding up."""
    if not text:
        return 0
    return int(len(text) / chars_per_token) + 1


def _boundary_before(text: str, start: int, end: int) -> int:
    """Find a natural split point at or before ``end``.

    Prefers a paragraph break, then a sentence end, then whitespace. Refuses to
    backtrack past the midpoint of the piece so that honouring a boundary can
    never collapse the chunk size and inflate the number of LLM calls.
    """
    floor = start + (end - start) // 2
    for separator in ("\n\n", ". ", "\n", " "):
        found = text.rfind(separator, floor, end)
        if found > floor:
            return found + len(separator)
    return end


def split_text(text: str, max_chars: int, overlap_chars: int = 0) -> List[str]:
    """Split ``text`` into the fewest pieces of at most ``max_chars``.

    Consecutive pieces share ``overlap_chars`` of context so that a sentence
    straddling a boundary is still readable in at least one piece. Overlap is
    clamped so that every iteration makes forward progress.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # An overlap at or above the chunk size would rewind further than each step
    # advances, so the loop would never reach the end of the text.
    overlap = max(0, min(overlap_chars, max_chars // 2))

    chunks: List[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            end = _boundary_before(text, start, end)
        chunks.append(text[start:end])
        if end >= length:
            break
        start = max(end - overlap, start + 1)

    return chunks


class ContextWindowResolver:
    """Resolve a model's usable input budget.

    Asks the client what window the server is actually serving, and falls back
    to the configured value when the provider cannot answer — which is the
    normal case at boot, before vLLM finishes loading the model.
    """

    def __init__(self, llm_client: Any, config: Any, logger: Any = None) -> None:
        self.llm_client = llm_client
        self.config = config
        self.logger = logger
        self._cache: dict = {}

    def _log(self, message: str, data: dict) -> None:
        if self.logger is None:
            return
        self.logger.log("service:text_window", message, data)

    def _configured_window(self) -> int:
        return int(getattr(self.config, "vllm_max_model_len", 0) or 4096)

    def _discover(self, model: str) -> Optional[int]:
        probe = getattr(self.llm_client, "get_context_window", None)
        if not callable(probe):
            return None
        try:
            window = probe(model)
        except Exception as exc:
            self._log("Context window discovery failed, using configured value", {"error": str(exc)})
            return None
        if not window or int(window) <= 0:
            return None
        return int(window)

    def context_tokens(self, model: str) -> int:
        """Return the model's total context window in tokens."""
        if model in self._cache:
            return self._cache[model]

        window = self._discover(model) or self._configured_window()
        self._cache[model] = window
        self._log("Resolved context window", {"model": model, "context_tokens": window})
        return window

    def input_budget_chars(
        self, model: str, reserved_tokens: int = 0, output_tokens: Optional[int] = None
    ) -> int:
        """Characters of source text that fit alongside the prompt and output.

        ``output_tokens`` is how many tokens the response is allowed to consume;
        it must match the ``max_tokens`` the caller will request so input and
        output together stay inside the window. Defaults to the chat cap.
        """
        if output_tokens is None:
            output_tokens = int(getattr(self.config, "vllm_max_tokens", 512) or 512)
        available = (
            self.context_tokens(model)
            - output_tokens
            - int(reserved_tokens)
            - SAFETY_MARGIN_TOKENS
        )
        if available <= 0:
            return MIN_BUDGET_CHARS
        return max(MIN_BUDGET_CHARS, int(available * DEFAULT_CHARS_PER_TOKEN))
