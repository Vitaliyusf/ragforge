"""Legacy and compatibility-focused Pydantic message helpers.

These models describe older flat or lightly structured Kafka request/response
shapes that are still imported by parts of `llm_agent`. They are not the
authoritative typed-envelope contract for the repository; the newer typed
message surfaces live in service-local schema modules such as
`backend/gateway/app/schemas/common.py`, `backend/llm_agent/app/schemas/llm.py`,
and `backend/vector_db/app/schemas/vector.py`.
"""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Standard HTTP error response shape (used by every FastAPI service)
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Standardized HTTP error response returned by every service endpoint.

    ``error``   — snake_case machine-readable code (e.g. ``gateway_timeout``)
    ``message`` — human-readable description for the client
    ``details`` — optional structured context (validation errors, etc.)
    """
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Base / shared
# ---------------------------------------------------------------------------

class CorrelatedRequest(BaseModel):
    """Legacy request shape that expects a `correlation_id` in the reply."""
    correlation_id: str


class KafkaResponse(BaseModel):
    """Legacy flat reply envelope written to `gateway_responses`."""
    correlation_id: str
    status: Literal["success", "error"]
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


# ---------------------------------------------------------------------------
# LLM agent requests
# ---------------------------------------------------------------------------

class LLMRequest(CorrelatedRequest):
    """Legacy plain text-generation request for non-typed handler paths."""
    prompt: str = Field(..., min_length=1)
    model: Optional[str] = None
    timeout: Optional[float] = None


class SummaryRequest(BaseModel):
    """Legacy fire-and-forget file summarization request."""
    file_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    model: Optional[str] = None
    prompt: Optional[str] = "TL;DR"


class MetadataRequest(BaseModel):
    """Legacy fire-and-forget metadata extraction request."""
    file_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    model: Optional[str] = None


class ModelRequest(CorrelatedRequest):
    """Simple model-listing request."""


class ModelManagementRequest(CorrelatedRequest):
    """Legacy model-management action request."""
    action: str = Field(..., min_length=1)
    model: Optional[str] = None
    implementation: Optional[str] = None


class ConfigManagementRequest(CorrelatedRequest):
    """Legacy effective-configuration read request."""
    action: Literal["get_config"]


class GenerateQuestionsRequest(BaseModel):
    """Legacy suggested-question generation request."""
    action: str = Field(..., min_length=1)
    file_id: str = Field(..., min_length=1)
    summary: Optional[str] = ""
    filename: Optional[str] = ""


# ---------------------------------------------------------------------------
# RAG service requests
# ---------------------------------------------------------------------------

class RAGRequest(CorrelatedRequest):
    """Legacy flat RAG pipeline request."""
    question: str = Field(..., min_length=1)
    answer_mode: str = "quick"
    model: Optional[str] = None
    history: Optional[str] = None


# ---------------------------------------------------------------------------
# Embedding service requests
# ---------------------------------------------------------------------------

class EmbeddingRequest(BaseModel):
    """Legacy text-embedding request."""
    text: str = Field(..., min_length=1)
    file_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Vector DB requests
# ---------------------------------------------------------------------------

class VectorSearchRequest(CorrelatedRequest):
    """Legacy vector-similarity search request."""
    vector: List[float] = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    text_query: Optional[str] = None


# ---------------------------------------------------------------------------
# Reranker requests
# ---------------------------------------------------------------------------

class RerankRequest(CorrelatedRequest):
    """Legacy cross-encoder rerank request."""
    query: str = Field(..., min_length=1)
    results: List[Dict[str, Any]] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Files service requests
# ---------------------------------------------------------------------------

class FileRequest(CorrelatedRequest):
    """Legacy flat file-action request."""
    action: str = Field(..., min_length=1)
    file_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Memory service requests
# ---------------------------------------------------------------------------

class MemoryRequest(CorrelatedRequest):
    """Legacy memory-service action request."""
    action: str = Field(..., min_length=1)
    chat_id: Optional[str] = None
    recent_count: Optional[int] = None
