"""Chat-exit orchestration for titles, memory curation, and compressed history."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.agent.memory_agent import MemoryAgent
from app.core.config import settings
from app.core.errors import DatabaseError
from app.core.logging_config import ServiceLogger
from app.services.chat_service import ChatService
from app.services.memory_service import LongTermMemoryService
from app.services.message_service import MessageService


def _normalize_vllm_base_url(base_url: str) -> str:
    """Return an OpenAI-compatible base URL that always ends in ``/v1``."""
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        normalized = "http://vllm:8000"
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


class ChatExitService:
    """Generate chat titles, curate memories, and store compressed summaries on chat exit."""

    def __init__(
        self,
        chat_service: ChatService,
        message_service: MessageService,
        memory_service: LongTermMemoryService,
        logger: ServiceLogger,
    ) -> None:
        """Store collaborators and initialize the direct vLLM-backed memory agent.

        Parameters:
            chat_service: Chat CRUD service used for title and summary updates.
            message_service: Message service used to load the exiting conversation.
            memory_service: Long-term memory service used by the memory curator.
            logger: Structured service logger.
        """
        self.chat_service = chat_service
        self.message_service = message_service
        self.memory_service = memory_service
        self.logger = logger
        self._vllm_base_url = _normalize_vllm_base_url(settings.vllm_base_url)
        self._vllm_api_key = settings.vllm_api_key or "none"
        self._model = settings.default_model
        self._memory_agent = MemoryAgent(memory_service, logger, self._vllm_base_url, self._model)

    def _request_llm_completion(
        self,
        prompt: str,
        timeout: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Request one non-streaming chat completion from the configured direct vLLM endpoint.

        Parameters:
            prompt: User-facing prompt text sent to the LLM.
            timeout: Request timeout in seconds.
            max_tokens: Maximum completion tokens requested from the model.

        Returns:
            The first completion text returned by the OpenAI-compatible endpoint.

        Raises:
            RuntimeError: If the endpoint returns no completion choices.
            OSError: Propagated from the HTTP layer on connection or timeout errors.
            ValueError: Propagated if the response body is not valid JSON.
        """
        request_timeout = timeout or settings.chat_exit_llm_timeout_seconds
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": max_tokens or settings.chat_exit_summary_max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._vllm_api_key}",
        }

        try:
            with httpx.Client(timeout=request_timeout) as client:
                response = client.post(
                    f"{self._vllm_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("The chat-exit LLM request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            raise RuntimeError(f"The chat-exit LLM request failed with status {status_code}.") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("The chat-exit LLM endpoint is unavailable.") from exc
        except ValueError as exc:
            raise RuntimeError("The chat-exit LLM returned an invalid JSON response.") from exc

        choices = result.get("choices") or []
        if not choices:
            raise RuntimeError("No completion choices returned by the LLM endpoint")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            return "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            ).strip()
        return str(content or "").strip()

    def _generate_headline(self, messages: List[Dict[str, Any]]) -> str:
        """Generate a short title from the first ten messages of the conversation."""
        if not messages:
            return "New Chat"

        conversation = "\n".join(
            f"{m.get('sender', 'Unknown')}: {m.get('message', '')}"
            for m in messages[:10]
        )
        prompt = (
            "Generate a concise headline (max 50 characters) for this conversation.\n\n"
            f"{conversation}\n\nHeadline:"
        )
        try:
            headline = self._request_llm_completion(
                prompt,
                timeout=settings.chat_exit_headline_timeout_seconds,
                max_tokens=settings.chat_exit_headline_max_tokens,
            ).strip().strip('"\'')
            return headline[:47] + "..." if len(headline) > 50 else (headline or "New Chat")
        except Exception as exc:
            self.logger.log("chat_exit_service:_generate_headline", "Error", {"error": str(exc)}, "E")
            return "New Chat"

    def _curate_memories(self, messages: List[Dict[str, Any]], chat_id: str) -> None:
        """Run the direct memory curator against the full chat transcript."""
        if not messages or len(messages) < 2:
            return

        conversation = "\n".join(
            f"{m.get('sender', 'Unknown')}: {m.get('message', '')}"
            for m in messages
        )
        self._memory_agent.run(conversation, chat_id)

    def _compress_history(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """Summarize the conversation into a compact prompt-ready history string."""
        if not messages:
            return None

        conversation = "\n".join(
            f"{m.get('sender', 'Unknown')}: {m.get('message', '')}"
            for m in messages
        )
        prompt = (
            "Summarise the following conversation in at most 5 concise sentences. "
            "Keep key facts, decisions, and outcomes. Omit pleasantries.\n\n"
            f"{conversation}\n\nSummary:"
        )
        try:
            summary = self._request_llm_completion(
                prompt,
                timeout=settings.chat_exit_summary_timeout_seconds,
                max_tokens=settings.chat_exit_summary_max_tokens,
            ).strip()
            if not summary:
                return None
            return summary[:800]
        except Exception as exc:
            self.logger.log("chat_exit_service:_compress_history", "Error", {"error": str(exc)}, "E")
            return None

    def _update_user_insight(self) -> None:
        """Skip deprecated user-insight regeneration while keeping compatibility surfaces callable."""
        self.logger.log(
            "chat_exit_service:_update_user_insight",
            "Skipping user_insight refresh because the compatibility surface is deprecated",
            {},
        )

    def process_chat_exit(self, chat_id: str) -> Dict[str, Any]:
        """Process one chat exit by updating title, memories, and compressed history.

        Parameters:
            chat_id: Identifier of the chat being finalized.

        Returns:
            A compatibility response with `status`, `headline`, and `memories_updated`.

        Raises:
            DatabaseError: If chat loading, memory curation, or chat updates fail unexpectedly.
        """
        try:
            try:
                current_chat = self.chat_service.get_chat(chat_id)
                current_title = current_chat.get("title", "New Chat")
            except Exception:
                current_title = "New Chat"

            messages = self.message_service.get_messages(chat_id)
            if not messages:
                return {"status": "success", "headline": None, "memories_updated": False}

            headline = None
            if current_title == "New Chat":
                headline = self._generate_headline(messages)
                if headline and headline != "New Chat":
                    self.chat_service.update_title(chat_id, headline)

            self._curate_memories(messages, chat_id)

            summary = self._compress_history(messages)
            if summary:
                self.chat_service.update_compressed_summary(chat_id, summary)

            try:
                self._update_user_insight()
            except Exception as exc:
                self.logger.log("chat_exit_service:process_chat_exit", "Insight update failed", {"error": str(exc)}, "E")

            self.logger.log(
                "chat_exit_service:process_chat_exit",
                "Chat exit processed",
                {"chat_id": chat_id, "headline": headline, "compressed": bool(summary)},
            )
            return {"status": "success", "headline": headline, "memories_updated": True}
        except Exception as exc:
            self.logger.log("chat_exit_service:process_chat_exit", "Error", {"chat_id": chat_id, "error": str(exc)}, "E")
            raise DatabaseError(f"Failed to process chat exit: {exc}")

    def close(self) -> None:
        """Release owned resources.

        The service no longer keeps Kafka resources open after the local LLM
        refactor, so this method is intentionally a no-op.
        """
        return None
