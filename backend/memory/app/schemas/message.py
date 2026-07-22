"""Pydantic schemas for message operations."""
from pydantic import BaseModel, Field


class MessageBase(BaseModel):
    """Stored chat-message document returned by the memory service."""
    id: str
    chat_id: str
    sender: str
    message: str
    timestamp: str


class MessageResponse(MessageBase):
    """HTTP response body for one chat message."""
    pass


class AddMessageRequest(BaseModel):
    """HTTP request payload for adding one message to a chat."""
    chat_id: str = Field(..., description="Chat identifier")
    message_id: str = Field(..., description="Unique message identifier")
    sender: str = Field(default="User", description="Message sender")
    message: str = Field(..., description="Message content")


class GetMessagesRequest(BaseModel):
    """Compatibility request model for fetching chat messages by identifier."""
    chat_id: str = Field(..., description="Chat identifier")


class MessageListResponse(BaseModel):
    """HTTP response body for ordered chat message history."""
    status: str = "success"
    messages: list[MessageResponse]
