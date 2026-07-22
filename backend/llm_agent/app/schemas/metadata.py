"""Pydantic schemas for metadata requests and responses."""
from pydantic import BaseModel, Field
from typing import List, Optional


class MetadataRequest(BaseModel):
    """Request model for metadata extraction."""
    file_id: str = Field(..., description="File identifier")
    text: str = Field(..., description="Text to extract metadata from")
    model: Optional[str] = Field(None, description="Model name to use (optional)")


class MetadataResponse(BaseModel):
    """Response model for metadata extraction."""
    keywords: List[str] = Field(..., description="Extracted keywords")
    file_id: str = Field(..., description="File identifier")


class ModelListResponse(BaseModel):
    """Response model for model list."""
    status: str = Field(..., description="Status of the request")
    models: List[str] = Field(..., description="List of available models")
    default: str = Field(..., description="Default model name")
    cached: bool = Field(..., description="Whether the list is from cache")
    last_updated: Optional[float] = Field(None, description="Timestamp of last cache update")
