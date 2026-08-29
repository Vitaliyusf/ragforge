"""Chat-exit orchestration through typed llm_agent requests."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aio_pika

from app.core.config import settings
from app.core.errors import DatabaseError
from app.services.chat_service import ChatService
from app.services.memory_service import LongTermMemoryService
from app.services.message_service import MessageService
from shared.auth import attach_internal_auth_context, verify_internal_ticket_from_envelope
from shared.logging import ServiceLogger


class ChatExitService:
    """Generate titles, curate memories, and compress chat history."""

    def __init__(
        self,
        chat_service: ChatService,
        message_service: MessageService,
        memory_service: LongTermMemoryService,
        logger: ServiceLogger,
    ) -> None:
        self.chat_service = chat_service
        self.message_service = message_service
        self.memory_service = memory_service
        self.logger = logger

    def _request_typed_llm(
        self,
        request_type: str,
        input_payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """Run one typed llm_agent RPC from the handler's worker thread."""
        return asyncio.run(self._request_typed_llm_async(request_type, input_payload, timeout))

    async def _request_typed_llm_async(
        self,
        request_type: str,
        input_payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        try:
            async with connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    settings.rabbitmq_exchange,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True,
                )
                reply_queue = await channel.declare_queue(exclusive=True, auto_delete=True)
                message_id = uuid4().hex
                envelope = attach_internal_auth_context(
                    {
                        "message_id": message_id,
                        "message_type": "command",
                        "action": request_type,
                        "source_service": settings.service_name,
                        "target_service": settings.llm_agent_queue,
                        "request_id": message_id,
                        "trace_id": message_id,
                        "correlation_id": message_id,
                        "reply_to": reply_queue.name,
                        "timestamp": int(time.time() * 1000),
                        "payload": {
                            "request_type": request_type,
                            "input": input_payload,
                            "timeout": timeout,
                            "metadata": {"source": "chat_exit"},
                        },
                    }
                )
                await exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(envelope).encode("utf-8"),
                        correlation_id=message_id,
                        reply_to=reply_queue.name,
                        content_type="application/json",
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=settings.llm_agent_queue,
                )
                try:
                    async with asyncio.timeout(timeout):
                        async with reply_queue.iterator() as iterator:
                            async for message in iterator:
                                async with message.process():
                                    if message.correlation_id and message.correlation_id != message_id:
                                        continue
                                    reply = json.loads(message.body)
                                    verify_internal_ticket_from_envelope(reply, required=True)
                                    if not reply.get("success"):
                                        error = reply.get("error") or {}
                                        raise RuntimeError(error.get("message") or "llm_agent request failed")
                                    parsed = (reply.get("payload") or {}).get("parsed_output")
                                    if not isinstance(parsed, dict):
                                        raise RuntimeError("llm_agent returned no parsed output")
                                    return parsed
                except TimeoutError as exc:
                    raise RuntimeError(f"llm_agent request timed out after {timeout:.1f}s") from exc
        finally:
            await connection.close()
        raise RuntimeError("llm_agent reply queue closed before a response arrived")

    @staticmethod
    def _conversation_history(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        history: List[Dict[str, str]] = []
        for message in messages:
            sender = str(message.get("sender", "user")).strip().lower()
            role = sender if sender in {"system", "user", "assistant", "tool"} else "user"
            history.append({"role": role, "content": str(message.get("message", ""))})
        return history

    def _generate_headline(self, messages: List[Dict[str, Any]]) -> str:
        if not messages:
            return "New Chat"
        try:
            result = self._request_typed_llm(
                "chat_title",
                {"conversation_history": self._conversation_history(messages[:10])},
                settings.chat_exit_headline_timeout_seconds,
            )
            headline = str(result.get("title") or "").strip().strip('"\'')
            return headline[:47] + "..." if len(headline) > 50 else (headline or "New Chat")
        except Exception as exc:
            self.logger.log("chat_exit_service:_generate_headline", "Error", {"error": str(exc)}, "E")
            return "New Chat"

    def generate_title(self, chat_id: str) -> Dict[str, Any]:
        try:
            current_chat = self.chat_service.get_chat(chat_id)
            current_title = current_chat.get("title", "New Chat")
        except Exception:
            current_title = "New Chat"
        if current_title != "New Chat":
            return {"status": "success", "title": current_title}
        messages = self.message_service.get_messages(chat_id)
        if not messages:
            return {"status": "success", "title": None}
        headline = self._generate_headline(messages)
        if headline and headline != "New Chat":
            self.chat_service.update_title(chat_id, headline)
            return {"status": "success", "title": headline}
        return {"status": "success", "title": None}

    def _curate_memories(self, messages: List[Dict[str, Any]], chat_id: str) -> None:
        if len(messages) < 2:
            return
        existing = [
            {
                "id": memory.get("id"),
                "content": memory.get("content"),
                "category": memory.get("category", ""),
            }
            for memory in self.memory_service.get_all_memories()
            if memory.get("category") != "user_insight"
        ]
        result = self._request_typed_llm(
            "memory_curation",
            {
                "conversation_history": self._conversation_history(messages),
                "existing_memory": existing,
            },
            settings.chat_exit_llm_timeout_seconds,
        )
        existing_ids = {str(memory["id"]) for memory in existing if memory.get("id")}
        for action in result.get("actions", []):
            action_type = action.get("action")
            memory_id = str(action.get("memory_id") or "")
            content = str(action.get("content") or "").strip()[:120]
            if action_type == "add" and content:
                self.memory_service.create_memory(
                    content,
                    action.get("category") or "chat_insight",
                    {"source": "llm_agent", "chat_id": chat_id},
                )
            elif action_type == "update" and memory_id in existing_ids and content:
                self.memory_service.update_memory(memory_id, content=content)
            elif action_type == "delete" and memory_id in existing_ids:
                self.memory_service.delete_memory(memory_id)

    def _compress_history(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        if not messages:
            return None
        try:
            result = self._request_typed_llm(
                "chat_summary",
                {"conversation_history": self._conversation_history(messages)},
                settings.chat_exit_summary_timeout_seconds,
            )
            summary = str(result.get("summary") or "").strip()
            return summary[:800] if summary else None
        except Exception as exc:
            self.logger.log("chat_exit_service:_compress_history", "Error", {"error": str(exc)}, "E")
            return None

    def _update_user_insight(self) -> None:
        self.logger.log(
            "chat_exit_service:_update_user_insight",
            "Skipping user_insight refresh because the compatibility surface is deprecated",
            {},
        )

    def process_chat_exit(self, chat_id: str) -> Dict[str, Any]:
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
            self._update_user_insight()
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
        """No persistent outbound resources are owned by this service."""
        return None
