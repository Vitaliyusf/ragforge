"""Chat service — routes chat requests to RAG or LLM with context preparation."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.chat_history_service import ChatHistoryService

from app.core.constants import MemoryAction, HISTORY_MESSAGE_LIMIT
from app.schemas.chat import ChatRequest
from app.services.base import BaseRPCService

# Optional prompt-injection guard
try:
    from shared.prompt_guard import PromptGuard
    _prompt_guard = PromptGuard()
except ImportError:
    _prompt_guard = None  # type: ignore[assignment]

_INJECTION_BLOCKED_MSG = (
    "Your message was flagged by our security system. Please rephrase your request."
)


class ChatService(BaseRPCService):
    """Routes chat requests to the RAG or LLM backend with enriched context."""

    def __init__(self, *args: Any, chat_history_service: Optional["ChatHistoryService"] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.chat_history_service = chat_history_service

    # ── Public API ──────────────────────────────────────────────────────────

    async def process_chat(self, request: ChatRequest) -> Dict[str, Any]:
        """Route the chat request to RAG or plain LLM.

        Raises:
            RPCTimeoutError: Request exceeded timeout.
            RPCConnectionError: RabbitMQ is not reachable.
        """
        self.logger.log(
            "chat_service:process_chat",
            "Chat request received",
            {
                "use_rag": request.use_rag,
                "message_length": len(request.message) if request.message else 0,
                "model": request.model,
                "timeout": self.config.default_timeout,
            },
        )

        prompt_guard_meta = self._check_prompt_injection(request.message)
        if prompt_guard_meta.get("prompt_guard_safe") is False:
            return {"response": _INJECTION_BLOCKED_MSG, "error": "prompt_injection_blocked", **prompt_guard_meta}

        try:
            result = await (self._process_rag_chat(request) if request.use_rag else self._process_llm_chat(request))
            if prompt_guard_meta:
                result.update(prompt_guard_meta)
            return result
        except Exception as e:
            self.logger.error("chat_service:process_chat", "Chat request error", e)
            raise

    # ── Private helpers ──────────────────────────────────────────────────────

    def _check_prompt_injection(self, message: Optional[str]) -> Dict[str, Any]:
        """Run optional prompt-injection guard; returns metadata dict (may be empty)."""
        if not _prompt_guard or not message:
            return {}
        result = _prompt_guard.check(message)
        meta = {
            "prompt_guard_safe": result.safe,
            "prompt_guard_score": result.risk_score,
            "prompt_guard_flags": result.flags,
        }
        if not result.safe:
            self.logger.log(
                "chat_service:prompt_guard",
                "Prompt injection BLOCKED",
                {"risk_score": result.risk_score, "flags": result.flags},
            )
        return meta

    def _format_history(self, messages: list) -> str:
        """Format the last N messages as a labelled conversation string."""
        if not messages:
            return ""
        lines = [
            f"[{m.get('sender', 'Unknown')}]: {m.get('message', m.get('text', m.get('content', '')))}"
            for m in messages[-HISTORY_MESSAGE_LIMIT:]
        ]
        return "\n".join(lines)

    async def _prepare_context(self, request: ChatRequest) -> Tuple[str, str, Optional[str]]:
        """Fetch independent user insight and conversation history concurrently.

        Returns:
            (user_insight, history_str, history_sent)
            history_sent equals history_str when history exists, else None.
        """
        async with asyncio.TaskGroup() as tasks:
            insight_task = tasks.create_task(self._fetch_user_insight())
            history_task = tasks.create_task(self._fetch_history(request))

        user_insight = insight_task.result()
        history, history_sent = history_task.result()
        return user_insight, history, history_sent

    async def _fetch_user_insight(self) -> str:
        """Fetch user insight from the memory service; returns empty string on failure."""
        try:
            response = await self._send(
                self.config.request_topics["memory"],
                {"action": MemoryAction.GET_USER_INSIGHT},
            )
            if response.get("status") == "success":
                return str(response.get("insight", ""))
        except Exception as e:
            self.logger.log(
                "chat_service:_fetch_user_insight",
                "Error fetching user insight, continuing without it",
                {"error": str(e)},
            )
        return ""

    async def _fetch_history(self, request: ChatRequest) -> Tuple[str, Optional[str]]:
        """Fetch compressed history; falls back to raw messages on failure."""
        if not request.chat_id:
            return "", None

        try:
            response = await self._send(
                self.config.request_topics["memory"],
                {
                    "action": MemoryAction.GET_COMPRESSED_HISTORY,
                    "chat_id": request.chat_id,
                    "recent_count": HISTORY_MESSAGE_LIMIT,
                },
            )
            if response.get("status") == "success":
                parts = []
                if summary := response.get("compressed_summary", ""):
                    parts.append(f"[Earlier conversation summary]: {summary}")
                if recent := response.get("recent_messages", []):
                    parts.append(self._format_history(recent))
                history = "\n".join(parts)
                return history, history or None
        except Exception as e:
            self.logger.log(
                "chat_service:_fetch_history",
                "Compressed history unavailable, falling back to raw messages",
                {"error": str(e)},
            )

        return await self._fetch_raw_history_fallback(request.chat_id)

    async def _fetch_raw_history_fallback(self, chat_id: str) -> Tuple[str, Optional[str]]:
        """Fallback: fetch raw messages via chat_history_service."""
        if not self.chat_history_service:
            return "", None
        try:
            msg_response = await self.chat_history_service.get_messages(chat_id)
            msg_list = msg_response.get("messages", msg_response.get("data", {}).get("messages", []))
            if msg_list:
                history = self._format_history(msg_list)
                return history, history
        except Exception as e:
            self.logger.log(
                "chat_service:_fetch_raw_history_fallback",
                "Error fetching fallback chat history",
                {"error": str(e)},
            )
        return "", None

    async def _process_rag_chat(self, request: ChatRequest) -> Dict[str, Any]:
        """Embed question with user context then call the RAG service."""
        user_insight, history, history_sent = await self._prepare_context(request)

        question = f"[User Context: {user_insight}] {request.message}" if user_insight else request.message

        self.logger.log(
            "chat_service:_process_rag_chat",
            "Sending request to RAG service",
            {
                "topic": self.config.request_topics["rag"],
                "has_user_insight": bool(user_insight),
                "has_history": bool(history),
            },
        )

        payload: Dict[str, Any] = {
            "question": question,
            "answer_mode": request.answer_mode.value,
        }
        if request.model:
            payload["model"] = request.model
        if history:
            payload["history"] = history

        response = await self._send_long(self.config.request_topics["rag"], payload)

        # Normalise key: RAG returns "answer", frontend expects "response"
        if "answer" in response and "response" not in response:
            response["response"] = response.pop("answer")
        if history_sent is not None:
            response["history_sent"] = history_sent

        self.logger.log(
            "chat_service:_process_rag_chat",
            "RAG response received",
            {"response_length": len(str(response))},
        )
        return response

    async def _process_llm_chat(self, request: ChatRequest) -> Dict[str, Any]:
        """Build a typed answer-generation request and call the LLM agent."""
        user_insight, history, history_sent = await self._prepare_context(request)

        instruction_parts = ["Answer the user's question directly and clearly."]
        if history:
            instruction_parts.append(f"Use this conversation history when relevant:\n{history}")
        if user_insight:
            instruction_parts.append(f"Use this user context when relevant: {user_insight}")
        instructions = "\n\n".join(instruction_parts)

        self.logger.log(
            "chat_service:_process_llm_chat",
            "Sending request to LLM agent",
            {
                "topic": self.config.request_topics["llm_agent"],
                "prompt_length": len(instructions) + len(request.message),
                "has_user_insight": bool(user_insight),
                "has_history": bool(history),
                "model": request.model,
            },
        )

        payload: Dict[str, Any] = {
            "action": "answer_generation",
            "request_type": "answer_generation",
            "model": request.model,
            "metadata": {
                "source": "gateway.chat",
                "chat_id": request.chat_id,
                "use_rag": False,
            },
            "debug": {"include_visible_reasoning_steps": False},
            "input": {
                "question": request.message,
                "retrieved_context": [],
                "instructions": instructions,
            },
        }

        response = await self._send_long(self.config.request_topics["llm_agent"], payload)
        parsed_output = response.get("parsed_output")
        answer = parsed_output.get("answer") if isinstance(parsed_output, dict) else None
        result: Dict[str, Any] = {
            "response": answer or response.get("raw_output", ""),
            "model": response.get("model") or request.model,
            "use_rag": False,
            "prompt_sent": f"{instructions}\n\nQuestion: {request.message}",
        }
        if history_sent is not None:
            result["history_sent"] = history_sent

        self.logger.log(
            "chat_service:_process_llm_chat",
            "LLM agent response received",
            {"response_length": len(result["response"])},
        )
        return result
