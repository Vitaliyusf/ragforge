"""Message-related Pydantic schemas."""
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator

from shared.chat_metadata import sanitize_chat_metadata


class MessageRequest(BaseModel):
    """Request model for adding a message."""
    sender: str = Field(default="User", description="Message sender")
    message: str = Field(..., description="The message content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Bounded durable turn metadata")

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_metadata(cls, value: Any) -> Dict[str, Any]:
        return sanitize_chat_metadata(value)


class MessageResponse(BaseModel):
    """Response model for a message."""
    message_id: str = Field(..., description="Message ID")
    chat_id: str = Field(..., description="Chat ID")
    sender: str = Field(..., description="Message sender")
    message: str = Field(..., description="The message content")
    timestamp: str = Field(..., description="Message timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Durable turn metadata")
