"""Fail-closed approval boundary for user-visible answer tokens."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.services.conversation_events import BaseConversationEmitter


@dataclass
class OutputApprovalBuffer:
    """Buffer one candidate answer until its output safety scan approves it.

    Starting a later generation (for example a revision) replaces the earlier
    candidate so a client can never receive a draft followed by a second,
    incompatible answer. Cancellation propagates normally; the timeout bounds
    the complete post-approval flush.
    """

    emitter: BaseConversationEmitter
    emit_timeout_seconds: float
    _source: str = "final"
    _tokens: list[tuple[str, int]] = field(default_factory=list)

    def start_candidate(self, source: str) -> None:
        self._source = source
        self._tokens.clear()

    async def buffer_token(self, text_delta: str, token_index: int) -> None:
        if text_delta:
            self._tokens.append((text_delta, token_index))

    def reject(self) -> None:
        self._tokens.clear()

    async def approve(self, final_answer: str) -> None:
        tokens = list(self._tokens)
        self._tokens.clear()
        streamed_answer = "".join(text for text, _ in tokens)
        if streamed_answer.rstrip() != final_answer.rstrip():
            tokens = [(final_answer, 0)] if final_answer else []

        async def emit_all() -> None:
            for text_delta, token_index in tokens:
                await self.emitter.emit(
                    "token",
                    {
                        "text_delta": text_delta,
                        "token_index": token_index,
                        "source": self._source,
                    },
                )

        await asyncio.wait_for(emit_all(), timeout=self.emit_timeout_seconds)
