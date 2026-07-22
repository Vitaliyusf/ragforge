"""Long-term memory service — memory entry CRUD and user-insight via the memory service."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.constants import MemoryAction
from app.services.base import BaseRPCService


class LongTermMemoryService(BaseRPCService):
    """RabbitMQ-backed facade for long-term-memory and user-insight operations."""

    async def get_all_memories(self) -> Dict[str, Any]:
        """Fetch all long-term-memory entries."""
        return await self._send(
            self.config.request_topics["memory"],
            {"action": MemoryAction.GET_LONG_TERM_MEMORIES},
        )

    async def create_memory(
        self,
        content: str,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new long-term-memory entry."""
        payload: Dict[str, Any] = {
            "action": MemoryAction.CREATE_LONG_TERM_MEMORY,
            "content": content,
        }
        if category:
            payload["category"] = category
        if metadata:
            payload["metadata"] = metadata
        return await self._send(self.config.request_topics["memory"], payload)

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update an existing long-term-memory entry."""
        payload: Dict[str, Any] = {
            "action": MemoryAction.UPDATE_LONG_TERM_MEMORY,
            "memory_id": memory_id,
        }
        if content is not None:
            payload["content"] = content
        if category is not None:
            payload["category"] = category
        if metadata is not None:
            payload["metadata"] = metadata
        return await self._send(self.config.request_topics["memory"], payload)

    async def delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """Delete a long-term-memory entry."""
        return await self._send(
            self.config.request_topics["memory"],
            {"action": MemoryAction.DELETE_LONG_TERM_MEMORY, "memory_id": memory_id},
        )

    async def get_user_insight(self) -> Dict[str, Any]:
        """Fetch the current user-insight summary."""
        return await self._send(
            self.config.request_topics["memory"],
            {"action": MemoryAction.GET_USER_INSIGHT},
        )

    async def update_user_insight(self, insight: str) -> Dict[str, Any]:
        """Replace the user-insight summary."""
        return await self._send(
            self.config.request_topics["memory"],
            {"action": MemoryAction.UPDATE_USER_INSIGHT, "insight": insight},
        )
