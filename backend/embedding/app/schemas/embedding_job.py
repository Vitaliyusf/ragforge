"""Strict Pydantic models for typed embedding-job Kafka messages.

These models describe the typed embedding-job path only.
"""
import json
from typing import Any, Dict, List, Literal, Optional, Type, TypeVar

from pydantic import BaseModel, Field


ModelT = TypeVar("ModelT", bound=BaseModel)

KafkaMessageType = Literal["command", "query", "reply", "event", "stream_event"]
ChunkReviewStatus = Literal["clean", "accepted_with_risk", "sanitized", "removed"]
UpsertReviewOutcome = Literal["none"]


class EmbeddingJobChunk(BaseModel):
    """Chunk payload accepted by the typed embedding-job worker."""

    file_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    chunk_index: int
    chunk_version: int
    text: str = Field(..., min_length=1)
    text_preview: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1)
    page: Optional[int] = None
    section: Optional[str] = None
    retrieval_allowed: bool
    review_status: ChunkReviewStatus
    issue_flags: List[str] = Field(default_factory=list)
    created_at: str = Field(..., min_length=1)
    tenant_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_admin_id: Optional[str] = None


class EmbeddedJobChunk(EmbeddingJobChunk):
    """Typed chunk payload enriched with an embedding vector."""

    embedding: List[float] = Field(default_factory=list)


class EmbeddingJobRequestedPayload(BaseModel):
    """Inbound payload for typed embedding.jobs.requested commands."""

    job_id: str = Field(..., min_length=1)
    file_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    requested_at: str = Field(..., min_length=1)
    chunks: List[EmbeddingJobChunk] = Field(default_factory=list)


class VectorDbUpsertRequestedPayload(BaseModel):
    """Outbound payload for typed vector_db.upsert.requested commands."""

    review_outcome: UpsertReviewOutcome = "none"
    collection_name: str = Field(..., min_length=1)
    chunks: List[EmbeddedJobChunk] = Field(default_factory=list)


class EmbeddingJobsCompletedPayload(BaseModel):
    """Outbound payload for typed embedding.jobs.completed events."""

    job_id: str = Field(..., min_length=1)
    file_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    status: str = Field(default="completed", min_length=1)
    requested_chunks: int
    embedded_chunks: int
    skipped_chunks: int
    batches_processed: int
    model_name: str = Field(..., min_length=1)
    vector_dimensions: int
    completed_at: str = Field(..., min_length=1)


class KafkaEnvelope(BaseModel):
    """Common typed Kafka envelope shared by typed cross-service messages."""

    message_id: str = Field(..., min_length=1)
    message_type: KafkaMessageType
    action: str = Field(..., min_length=1)
    source_service: str = Field(..., min_length=1)
    target_service: str = Field(..., min_length=1)
    request_id: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    reply_to: Optional[str] = None
    stream_to: Optional[str] = None
    timestamp: str = Field(..., min_length=1)
    payload: Dict[str, Any]


class EmbeddingJobRequestedEnvelope(KafkaEnvelope):
    """Typed envelope required by the embedding-job worker."""

    message_type: Literal["command"] = "command"
    action: Literal["process_embedding_job"] = "process_embedding_job"
    source_service: Literal["files"] = "files"
    target_service: Literal["embedding"] = "embedding"
    payload: EmbeddingJobRequestedPayload


class VectorDbUpsertRequestedEnvelope(KafkaEnvelope):
    """Typed envelope published to the vector-db service."""

    message_type: Literal["command"] = "command"
    action: Literal["upsert_chunks"] = "upsert_chunks"
    source_service: Literal["embedding"] = "embedding"
    target_service: Literal["vector_db"] = "vector_db"
    payload: VectorDbUpsertRequestedPayload


class EmbeddingJobsCompletedEnvelope(KafkaEnvelope):
    """Typed completion event emitted after embedding-job processing."""

    message_type: Literal["event"] = "event"
    action: Literal["embedding_job_completed"] = "embedding_job_completed"
    source_service: Literal["embedding"] = "embedding"
    target_service: Literal["platform"] = "platform"
    payload: EmbeddingJobsCompletedPayload


def parse_model(model_cls: Type[ModelT], payload: Dict[str, Any]) -> ModelT:
    """Parse a payload into a Pydantic model across Pydantic versions."""
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(payload)
    return model_cls.parse_obj(payload)


def model_to_dict(model: BaseModel, *, exclude_none: bool = False) -> Dict[str, Any]:
    """Serialize a Pydantic model into a JSON-safe dict across Pydantic versions."""
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json", exclude_none=exclude_none)
    return json.loads(model.json(exclude_none=exclude_none))
