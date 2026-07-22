"""Chat-related Pydantic schemas."""
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.core.constants import AnswerMode


class ChatRequest(BaseModel):
    """Request model for chat."""
    message: str = Field(..., description="The chat message")
    use_rag: bool = Field(default=False, description="Whether to use RAG")
    model: Optional[str] = Field(default=None, description="Model to use")
    chat_id: Optional[str] = Field(default=None, description="Chat ID for conversation history context")
    answer_mode: AnswerMode = Field(default=AnswerMode.QUICK, description="Answer verbosity: 'quick' or 'extended'")


class ChatResponse(BaseModel):
    """Response model for chat."""
    response: str = Field(..., description="The chat response")
    model: Optional[str] = Field(default=None, description="Model used")
    use_rag: Optional[bool] = Field(default=None, description="Whether RAG was used")
    sources: Optional[List[Any]] = Field(default=None, description="RAG sources with metadata")
    prompt_sent: Optional[str] = Field(default=None, description="Full prompt sent to LLM")
    history_sent: Optional[str] = Field(default=None, description="Conversation history included in prompt")
