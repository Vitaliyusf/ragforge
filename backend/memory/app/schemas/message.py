"""Pydantic schemas for message operations."""
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator

from shared.chat_metadata import sanitize_chat_metadata


class MessageBase(BaseModel):
    """Stored chat-message document returned by the memory service."""
    id: str
    chat_id: str
    sender: str
    message: str
    timestamp: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageResponse(MessageBase):
    """HTTP response body for one chat message."""
    pass


class AddMessageRequest(BaseModel):
    """HTTP request payload for adding one message to a chat."""
    chat_id: str = Field(..., description="Chat identifier")
    message_id: str = Field(..., description="Unique message identifier")
    sender: str = Field(default="User", description="Message sender")
    message: str = Field(..., description="Message content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Bounded durable turn metadata")

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_metadata(cls, value: Any) -> Dict[str, Any]:
        return sanitize_chat_metadata(value)


class GetMessagesRequest(BaseModel):
    """Compatibility request model for fetching chat messages by identifier."""
    chat_id: str = Field(..., description="Chat identifier")


class MessageListResponse(BaseModel):
    """HTTP response body for ordered chat message history."""
    status: str = "success"
    messages: list[MessageResponse]
