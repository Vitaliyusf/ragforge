"""Frontend event helpers for the direct WebSocket runtime."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from app.services.conversation_types import ConversationRequest, utc_now_iso


ALLOWED_EVENT_TYPES = {"status", "trace", "token", "answer_review", "done", "error"}


def build_event(
    event_type: str,
    request: ConversationRequest,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a standardized frontend event envelope."""
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"Unsupported event type: {event_type}")
    return {
        "type": event_type,
        "request_id": request.request_id,
        "trace_id": request.trace_id,
        "conversation_id": request.conversation_id,
        "turn_id": request.turn_id,
        "timestamp": utc_now_iso(),
        "data": data,
    }


def build_error_event(
    request: ConversationRequest,
    *,
    code: str,
    failed_node: str,
    retryable: bool,
    message: str,
    origin_service: str = "rag",
    origin_location: str = "conversation_graph",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a standard error event envelope."""
    return build_event(
        "error",
        request,
        {
            "code": code,
            "failed_node": failed_node,
            "retryable": retryable,
            "message": message,
            "origin": {
                "service": origin_service,
                "location": origin_location,
            },
            "details": details or {},
            "correlation_id": request.correlation_id,
        },
    )


class BaseConversationEmitter:
    """Base emitter for frontend events."""

    def __init__(self, request: ConversationRequest):
        self.request = request
        self._terminal_sent = False
        self.events: List[Dict[str, Any]] = []

    async def emit(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Emit a standardized event."""
        if self._terminal_sent and event_type in {"done", "error"}:
            return {}
        # Trace and model-debug payloads are operational data.  They can expose
        # prompts, model output and internal decisions, so they never cross the
        # socket boundary for regular users even if a client asks for them.
        if self.request.role != "admin" and event_type == "trace":
            return {}
        public_data = deepcopy(data)
        if self.request.role != "admin" and event_type == "done":
            public_data.pop("trace_summary", None)
            public_data.pop("safe_debug_payloads", None)
            public_data.pop("debug_payloads", None)
        event = build_event(event_type, self.request, public_data)
        if event_type in {"done", "error"}:
            self._terminal_sent = True
        self.events.append(event)
        await self._publish(event_type, event)
        return event

    async def _publish(self, event_type: str, event: Dict[str, Any]) -> None:
        """Publish implementation hook."""
        raise NotImplementedError

    @property
    def terminal_sent(self) -> bool:
        """Whether a terminal event has already been emitted."""
        return self._terminal_sent


class SocketIOConversationEmitter(BaseConversationEmitter):
    """Socket.IO-backed event emitter."""

    def __init__(self, request: ConversationRequest, sio: Any, sid: str):
        super().__init__(request)
        self.sio = sio
        self.sid = sid

    async def _publish(self, event_type: str, event: Dict[str, Any]) -> None:
        await self.sio.emit(event_type, event, room=self.sid)


class CollectingConversationEmitter(BaseConversationEmitter):
    """Emitter used by tests and synchronous entrypoints."""

    async def _publish(self, event_type: str, event: Dict[str, Any]) -> None:
        return None

    def latest(self, event_type: str) -> Optional[Dict[str, Any]]:
        """Return the latest event of a type."""
        for event in reversed(self.events):
            if event["type"] == event_type:
                return event
        return None
