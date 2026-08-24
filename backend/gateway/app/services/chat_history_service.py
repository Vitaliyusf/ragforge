"""Chat history service — chat and message CRUD via the memory service."""
from __future__ import annotations

import uuid
from typing import Any, Dict

from app.schemas.message import MessageRequest
from app.core.constants import MemoryAction
from app.services.base import BaseRPCService


class ChatHistoryService(BaseRPCService):
    """RabbitMQ-backed facade for chat and message CRUD in the memory service."""

    async def create_chat(self, title: str = "New Chat") -> Dict[str, Any]:
        """Create a new chat session."""
        return await self._send(
            self.config.request_topics["memory"],
            {"action": MemoryAction.CREATE_CHAT, "chat_id": str(uuid.uuid4()), "title": title},
        )

    async def get_chats(self) -> Dict[str, Any]:
        """Return all chat sessions."""
        return await self._send(
            self.config.request_topics["memory"],
            {"action": MemoryAction.GET_CHATS},
        )

    async def get_messages(self, chat_id: str) -> Dict[str, Any]:
        """Return all messages for a chat."""
        return await self._send(
            self.config.request_topics["memory"],
            {"action": MemoryAction.GET_MESSAGES, "chat_id": chat_id},
        )

    async def add_message(self, chat_id: str, request: MessageRequest) -> Dict[str, Any]:
        """Append a message to a chat."""
        return await self._send(
            self.config.request_topics["memory"],
            {
                "action": MemoryAction.ADD_MESSAGE,
                "chat_id": chat_id,
                "message_id": str(uuid.uuid4()),
                "sender": request.sender,
                "message": request.message,
            },
        )

    async def delete_chat(self, chat_id: str) -> Dict[str, Any]:
        """Delete a chat and all its messages."""
        return await self._send(
            self.config.request_topics["memory"],
            {"action": MemoryAction.DELETE_CHAT, "chat_id": chat_id},
        )

    async def process_chat_exit(self, chat_id: str) -> Dict[str, Any]:
        """Generate headline and extract memory on chat exit (LLM-backed, uses long timeout)."""
        return await self._send_long(
            self.config.request_topics["memory"],
            {"action": MemoryAction.PROCESS_CHAT_EXIT, "chat_id": chat_id},
        )

    async def generate_title(self, chat_id: str) -> Dict[str, Any]:
        """Idempotently name an untitled chat from its transcript (LLM-backed)."""
        return await self._send_long(
            self.config.request_topics["memory"],
            {"action": MemoryAction.GENERATE_TITLE, "chat_id": chat_id},
        )

    async def update_chat_title(self, chat_id: str, title: str) -> Dict[str, Any]:
        """Update the title of an existing chat."""
        return await self._send(
            self.config.request_topics["memory"],
            {"action": MemoryAction.UPDATE_CHAT_TITLE, "chat_id": chat_id, "title": title},
        )
