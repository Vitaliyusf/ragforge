"""Message-related Pydantic schemas."""
from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    """Request model for adding a message."""
    sender: str = Field(default="User", description="Message sender")
    message: str = Field(..., description="The message content")


class MessageResponse(BaseModel):
    """Response model for a message."""
    message_id: str = Field(..., description="Message ID")
    chat_id: str = Field(..., description="Chat ID")
    sender: str = Field(..., description="Message sender")
    message: str = Field(..., description="The message content")
    timestamp: str = Field(..., description="Message timestamp")
