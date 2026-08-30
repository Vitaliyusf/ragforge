"""Schemas for chunk-native vector operations and Kafka envelopes."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.constants import MAX_VERIFY_IDS


KafkaMessageType = Literal["command", "query", "reply", "event", "stream_event"]
ChunkReviewStatus = Literal[
    "clean",
    "accepted_with_risk",
    "sanitized",
    "removed",
]
UpsertReviewOutcome = Literal[
    "none",
    "remove_problematic_text",
    "accept_as_is",
]
DeleteReviewOutcome = Literal[
    "none",
    "delete_file",
]


class ChunkFilters(BaseModel):
    """Allowed caller filters for chunk search."""

    file_id: Optional[str] = None
    document_id: Optional[str] = None
    chunk_version: Optional[int] = None
    review_status: Optional[ChunkReviewStatus] = None
    page: Optional[int] = None
    section: Optional[str] = None
    tenant_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_admin_id: Optional[str] = None

    model_config = {"extra": "ignore"}


class ChunkDeleteFilters(BaseModel):
    """Supported hard-delete filters."""

    file_id: Optional[str] = None
    document_id: Optional[str] = None
    tenant_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_admin_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_scope(self) -> "ChunkDeleteFilters":
        if not self.file_id and not self.document_id:
            raise ValueError("filters must include file_id, document_id, or both")
        return self

    model_config = {"extra": "ignore"}


class ChunkPayloadModel(BaseModel):
    """Shared chunk contract for vector_db input."""

    file_id: str
    document_id: str
    chunk_id: str
    chunk_index: int
    chunk_version: int
    text: str
    text_preview: str
    source_name: str
    page: Optional[int] = None
    section: Optional[str] = None
    retrieval_allowed: bool
    review_status: ChunkReviewStatus
    issue_flags: List[str] = Field(default_factory=list)
    created_at: str
    tenant_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_admin_id: Optional[str] = None

    model_config = {"extra": "ignore"}


class ChunkUpsertItem(ChunkPayloadModel):
    """Chunk payload plus embedding vector."""

    embedding: List[float]

    model_config = {"extra": "ignore"}


class SparseVectorModel(BaseModel):
    """JSON-safe Qdrant sparse vector."""

    indices: List[int] = Field(default_factory=list, max_length=512)
    values: List[float] = Field(default_factory=list, max_length=512)

    @model_validator(mode="after")
    def validate_lengths(self) -> "SparseVectorModel":
        if len(self.indices) != len(self.values):
            raise ValueError("indices and values must have equal length")
        return self


class KafkaEnvelopeBase(BaseModel):
    """Common Kafka envelope fields shared across services."""

    message_id: str
    message_type: KafkaMessageType
    action: str
    source_service: str
    target_service: str
    request_id: str
    trace_id: str
    correlation_id: str
    reply_to: Optional[str] = None
    stream_to: Optional[str] = None
    timestamp: str

    model_config = {"extra": "ignore"}


class SearchChunksPayload(BaseModel):
    """Canonical search request payload."""

    query_vector: List[float]
    query_sparse: Optional[SparseVectorModel] = None
    retrieval_strategy: Literal["dense", "hybrid"] = "dense"
    top_k: int = Field(default=10, ge=1, le=100)
    dense_candidate_k: int = Field(default=20, ge=1, le=100)
    sparse_candidate_k: int = Field(default=20, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    filters: ChunkFilters = Field(default_factory=ChunkFilters)
    include_payload: bool = True
    include_vector: bool = False

    model_config = {"extra": "ignore"}


class VerifyChunkIdsPayload(BaseModel):
    """Read-only existence check for caller-supplied chunk and file ids.

    **There is deliberately no ``filters`` field.** Scope is derived entirely
    from the caller's trusted identity in ``VectorService``, so this payload
    offers no way to widen a lookup beyond the caller's own tenant. It is the
    reason this action is not a scroll: a caller can only ask about ids it
    already holds, and only within the scope it could already search.
    """

    chunk_ids: List[str] = Field(default_factory=list, max_length=MAX_VERIFY_IDS)
    file_ids: List[str] = Field(default_factory=list, max_length=MAX_VERIFY_IDS)

    @model_validator(mode="after")
    def validate_targets(self) -> "VerifyChunkIdsPayload":
        if not self.chunk_ids and not self.file_ids:
            raise ValueError("chunk_ids, file_ids, or both are required")
        return self

    model_config = {"extra": "ignore"}


class UpsertChunksPayload(BaseModel):
    """Canonical upsert request payload."""

    review_outcome: UpsertReviewOutcome = "none"
    target_filters: Optional[ChunkDeleteFilters] = None
    chunks: List[ChunkUpsertItem]

    @model_validator(mode="after")
    def validate_target_filters(self) -> "UpsertChunksPayload":
        if self.review_outcome == "remove_problematic_text" and self.target_filters is None:
            raise ValueError("target_filters is required for remove_problematic_text")
        return self

    model_config = {"extra": "ignore"}


class DeleteChunksPayload(BaseModel):
    """Canonical delete request payload after topic-level compatibility normalization."""

    review_outcome: DeleteReviewOutcome = "none"
    filters: ChunkDeleteFilters

    model_config = {"extra": "ignore"}


class InitializeCollectionPayload(BaseModel):
    """Canonical initialize request payload."""

    model_config = {"extra": "ignore"}


class SearchChunksRequest(KafkaEnvelopeBase):
    """Canonical Kafka search request."""

    message_type: Literal["query"] = "query"
    action: Literal["search_chunks"] = "search_chunks"
    reply_to: str
    payload: SearchChunksPayload


class VerifyChunkIdsRequest(KafkaEnvelopeBase):
    """Canonical RPC request for golden-set label verification."""

    message_type: Literal["query"] = "query"
    action: Literal["verify_chunk_ids"] = "verify_chunk_ids"
    payload: VerifyChunkIdsPayload


class UpsertChunksRequest(KafkaEnvelopeBase):
    """Canonical Kafka upsert request."""

    message_type: Literal["command"] = "command"
    action: Literal["upsert_chunks"] = "upsert_chunks"
    payload: UpsertChunksPayload


class DeleteChunksRequest(KafkaEnvelopeBase):
    """Canonical Kafka delete request consumed on `vector_db.delete.requested`."""

    message_type: Literal["command"] = "command"
    action: Literal["delete_chunks"] = "delete_chunks"
    payload: DeleteChunksPayload


class InitializeCollectionRequest(KafkaEnvelopeBase):
    """Canonical Kafka initialize request."""

    message_type: Literal["command"] = "command"
    action: Literal["initialize_collection"] = "initialize_collection"
    payload: InitializeCollectionPayload = Field(default_factory=InitializeCollectionPayload)


class KafkaReplyEnvelope(KafkaEnvelopeBase):
    """Canonical reply envelope."""

    message_type: Literal["reply"] = "reply"
    success: bool
    payload: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None


class UpsertCompletedPayload(BaseModel):
    """Canonical completion event payload."""

    completed_at: str
    status: str
    collection_name: str
    document_id: Optional[str] = None
    file_id: Optional[str] = None
    review_outcome: str
    upserted_count: int
    deleted_count: int
    message: str
    error: Optional[str] = None

    model_config = {"extra": "ignore"}


class UpsertCompletedEvent(KafkaEnvelopeBase):
    """Canonical upsert completion event."""

    message_type: Literal["event"] = "event"
    action: Literal["upsert_chunks"] = "upsert_chunks"
    event_type: Literal["vector_db.upsert.completed"] = "vector_db.upsert.completed"
    payload: UpsertCompletedPayload


class ChunkSearchApiRequest(BaseModel):
    """REST request for local/admin chunk search."""

    query_vector: List[float]
    query_sparse: Optional[SparseVectorModel] = None
    retrieval_strategy: Literal["dense", "hybrid"] = "dense"
    top_k: int = Field(default=10, ge=1, le=100)
    dense_candidate_k: int = Field(default=20, ge=1, le=100)
    sparse_candidate_k: int = Field(default=20, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    filters: ChunkFilters = Field(default_factory=ChunkFilters)
    include_payload: bool = True
    include_vector: bool = False


class ChunkUpsertApiRequest(BaseModel):
    """REST request for local/admin chunk upsert."""

    review_outcome: UpsertReviewOutcome = "none"
    target_filters: Optional[ChunkDeleteFilters] = None
    chunks: List[ChunkUpsertItem]

    @model_validator(mode="after")
    def validate_target_filters(self) -> "ChunkUpsertApiRequest":
        if self.review_outcome == "remove_problematic_text" and self.target_filters is None:
            raise ValueError("target_filters is required for remove_problematic_text")
        return self


class ChunkDeleteApiRequest(BaseModel):
    """REST request for local/admin chunk delete."""

    filters: ChunkDeleteFilters


class ChunkSearchResult(BaseModel):
    """Search result returned by REST endpoints."""

    id: str
    score: float
    payload: Optional[Dict[str, Any]] = None
    vector: Optional[List[float]] = None


class ChunkOperationResponse(BaseModel):
    """Generic REST response model."""

    success: bool
    message: str
    collection_name: Optional[str] = None
    upserted_count: Optional[int] = None
    deleted_count: Optional[int] = None
    results: Optional[List[ChunkSearchResult]] = None
