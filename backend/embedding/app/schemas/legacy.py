"""Pydantic schemas for legacy flat embedding and extraction endpoints."""
from typing import List

from pydantic import BaseModel


class EmbeddingRequest(BaseModel):
    text: str


class EmbeddingResponse(BaseModel):
    embedding: List[float]


class ExtractRequest(BaseModel):
    file_id: str
    path: str
    filename: str
