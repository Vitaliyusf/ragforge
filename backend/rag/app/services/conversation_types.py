"""Core types for the LangGraph-backed conversation runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, TypedDict
from uuid import uuid4


Mode = Literal["regular", "extended"]
OwnerType = Literal["user", "session", "conversation"]


class ConversationState(TypedDict):
    """Serializable graph state."""

    conversation_id: str
    turn_id: str
    mode: Mode
    user_message: str
    short_term_summary: str
    recent_messages: List[Dict[str, Any]]
    memory_hits: List[Dict[str, Any]]
    retrieved_chunks: List[Dict[str, Any]]
    retrieval_plan: Dict[str, Any]
    draft_answer: Dict[str, Any]
    answer_review: Dict[str, Any]
    trace_events: List[Dict[str, Any]]
    debug_payloads: Dict[str, Any]


@dataclass
class ConversationRequest:
    """Normalized request entering the conversation graph."""

    user_message: str
    mode: Mode = "regular"
    model: Optional[str] = None
    conversation_id: str = field(default_factory=lambda: str(uuid4()))
    turn_id: str = field(default_factory=lambda: str(uuid4()))
    request_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    graph_run_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: Optional[str] = None
    owner_id: Optional[str] = None
    owner_type: Optional[OwnerType] = None
    session_id: Optional[str] = None
    connection_id: Optional[str] = None
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    role: Optional[str] = None
    admin_id: Optional[str] = None
    history: Optional[str] = None
    raw_mode: Optional[str] = None
    debug: bool = True

    def __post_init__(self) -> None:
        """Normalize owner identity for feedback and memory aggregation."""
        if self.user_id:
            self.owner_id = self.user_id
            self.owner_type = "user"
            return
        if self.owner_type == "session" and not self.owner_id and self.session_id:
            self.owner_id = self.session_id
        if self.owner_type == "conversation" and not self.owner_id:
            self.owner_id = self.conversation_id
        if self.owner_id:
            self.owner_type = self.owner_type or "user"
        else:
            self.owner_id = self.conversation_id
            self.owner_type = "conversation"

    def owner_key(self) -> str:
        """Stable owner key for memory-feedback aggregation."""
        return self.owner_id or self.conversation_id


def utc_now_iso() -> str:
    """Current UTC timestamp in ISO8601."""
    return datetime.now(timezone.utc).isoformat()


def normalize_mode(
    mode: Optional[str] = None,
    answer_mode: Optional[str] = None,
) -> Mode:
    """Normalize the public request mode and the legacy answer_mode alias."""
    raw = (mode or answer_mode or "regular").strip().lower()
    if raw == "quick":
        return "regular"
    if raw == "extended":
        return "extended"
    return "regular"


def build_initial_state(request: ConversationRequest) -> ConversationState:
    """Build an empty, JSON-serializable graph state."""
    return ConversationState(
        conversation_id=request.conversation_id,
        turn_id=request.turn_id,
        mode=request.mode,
        user_message=request.user_message,
        short_term_summary=request.history or "",
        recent_messages=[],
        memory_hits=[],
        retrieved_chunks=[],
        retrieval_plan={},
        draft_answer={},
        answer_review={},
        trace_events=[],
        debug_payloads={},
    )
