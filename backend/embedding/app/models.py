"""Pydantic models for the embedding service."""
from pydantic import BaseModel
from typing import List


class EmbeddingRequest(BaseModel):
    """Request model for embedding generation."""
    text: str


class EmbeddingResponse(BaseModel):
    """Response model for embedding generation."""
    embedding: List[float]


class ExtractRequest(BaseModel):
    """Request model for file extraction."""
    file_id: str
    path: str
    filename: str
