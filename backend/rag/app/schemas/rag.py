"""HTTP request and response schemas for the secondary `rag` query endpoint."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RAGRequest(BaseModel):
    """Request body for the secondary HTTP query interface."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "What is the capital of France?",
                "model": "gpt-4",
                "mode": "regular",
                "answer_mode": "quick",
            }
        }
    )

    question: str = Field(..., min_length=1, description="The question to answer")
    model: Optional[str] = Field(None, description="Optional model name to use")
    mode: Optional[str] = Field(None, description="Conversation mode: 'regular' or 'extended'")
    answer_mode: Optional[str] = Field("quick", description="Legacy alias: 'quick' or 'extended'")


class RAGResponse(BaseModel):
    """Compact HTTP response body returned by the secondary query helper."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "The capital of France is Paris.",
                "sources": [
                    "Paris is the capital and most populous city of France...",
                    "France is a country in Western Europe...",
                ],
                "review": {"verdict": "pass"},
            }
        }
    )

    answer: str = Field(..., description="The generated answer")
    sources: List[Any] = Field(default_factory=list, description="Source text snippets returned by the query helper")
    review: Dict[str, Any] = Field(default_factory=dict, description="Answer evaluation payload")
