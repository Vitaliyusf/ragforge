"""Common schemas shared across the gateway service."""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field


MessageType = Literal["command", "query", "reply", "event", "stream_event"]


class MessageEnvelope(BaseModel):
    """Transport-neutral message envelope emitted by the gateway."""

    message_id: str = Field(..., description="Unique message id")
    message_type: MessageType = Field(..., description="Message type")
    action: str = Field(..., description="Action requested from the target service")
    source_service: str = Field(..., description="Originating service name")
    target_service: str = Field(..., description="Destination service name")
    request_id: str = Field(..., description="Frontend request identifier")
    trace_id: str = Field(..., description="Distributed trace identifier")
    correlation_id: str = Field(..., description="RPC request/reply correlation id")
    reply_to: Optional[str] = Field(default=None, description="Reply queue name")
    stream_to: Optional[str] = Field(default=None, description="Stream queue name")
    timestamp: int = Field(..., description="Unix epoch in milliseconds")
    auth_context: str = Field(..., description="Short-lived signed internal identity context")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Business payload")


class ReplyEnvelope(BaseModel):
    """Transport-neutral reply envelope consumed by the gateway."""

    message_id: str = Field(..., description="Unique reply message id")
    message_type: Literal["reply"] = Field(..., description="Reply message type")
    action: str = Field(..., description="Action being replied to")
    source_service: str = Field(..., description="Service publishing the reply")
    target_service: Literal["gateway"] = Field(..., description="Reply destination")
    request_id: str = Field(..., description="Frontend request identifier")
    trace_id: str = Field(..., description="Distributed trace identifier")
    correlation_id: str = Field(..., description="RPC request/reply correlation id")
    success: bool = Field(..., description="Whether the request succeeded")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Reply payload")
    error: Optional[Union[Dict[str, Any], str]] = Field(default=None, description="Optional error payload")
