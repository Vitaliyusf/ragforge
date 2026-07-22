"""Pydantic schemas for chat operations."""
from pydantic import BaseModel, Field


class ChatBase(BaseModel):
    """Stored chat document returned by the memory service."""
    id: str
    title: str
    created_at: str
    updated_at: str


class ChatResponse(ChatBase):
    """HTTP response body for one chat record."""
    pass


class CreateChatRequest(BaseModel):
    """HTTP request payload for chat creation."""
    chat_id: str = Field(..., description="Unique chat identifier")
    title: str = Field(default="New Chat", description="Chat title")


class ChatListResponse(BaseModel):
    """HTTP response body for chat list requests."""
    status: str = "success"
    chats: list[ChatResponse]
