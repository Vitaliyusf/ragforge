"""Pydantic schemas for summary requests and responses."""
from pydantic import BaseModel, Field
from typing import Optional


class SummaryRequest(BaseModel):
    """Request model for summary generation."""
    file_id: str = Field(..., description="File identifier")
    text: str = Field(..., description="Text to summarize")
    prompt: str = Field(default="TL;DR", description="Prompt prefix for summarization")
    model: Optional[str] = Field(None, description="Model name to use (optional)")


class SummaryResponse(BaseModel):
    """Response model for summary generation."""
    summary: str = Field(..., description="Generated summary")
    file_id: str = Field(..., description="File identifier")
