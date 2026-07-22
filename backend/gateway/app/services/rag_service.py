"""RAG service — trace retrieval and feedback submission via the RAG service."""
from __future__ import annotations

from typing import Any, Dict

from app.core.constants import RagAction
from app.core.correlation import add_correlation_metadata
from app.services.base import BaseRPCService


class RagService(BaseRPCService):
    """RabbitMQ-backed facade for RAG trace and feedback operations."""

    async def get_trace(self, requested_trace_id: str) -> Dict[str, Any]:
        """Fetch a trace from the RAG service."""
        response = await self._send(
            self.config.request_topics["rag"],
            {"action": RagAction.GET_TRACE, "requested_trace_id": requested_trace_id},
        )
        return add_correlation_metadata(response)

    async def submit_feedback(self, feedback: Dict[str, Any]) -> Dict[str, Any]:
        """Submit feedback to the RAG service."""
        response = await self._send(
            self.config.request_topics["rag"],
            {"action": RagAction.SUBMIT_FEEDBACK, **feedback},
        )
        return add_correlation_metadata(response)
