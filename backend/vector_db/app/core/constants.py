"""Domain constants and enums for the vector_db service.

All magic strings, action names, and DB field definitions live here.
No other module should hard-code these values.
"""
from enum import Enum


# ---------------------------------------------------------------------------
# Kafka message types
# ---------------------------------------------------------------------------

class MessageType(str, Enum):
    COMMAND = "command"
    QUERY = "query"
    REPLY = "reply"
    EVENT = "event"
    STREAM_EVENT = "stream_event"


# ---------------------------------------------------------------------------
# Vector DB actions
# ---------------------------------------------------------------------------

class VectorAction(str, Enum):
    SEARCH_CHUNKS = "search_chunks"
    UPSERT_CHUNKS = "upsert_chunks"
    DELETE_CHUNKS = "delete_chunks"
    INITIALIZE_COLLECTION = "initialize_collection"


# ---------------------------------------------------------------------------
# Review / delete outcomes
# ---------------------------------------------------------------------------

class UpsertReviewOutcome(str, Enum):
    NONE = "none"
    REMOVE_PROBLEMATIC_TEXT = "remove_problematic_text"
    ACCEPT_AS_IS = "accept_as_is"


class DeleteReviewOutcome(str, Enum):
    NONE = "none"
    DELETE_FILE = "delete_file"


# ---------------------------------------------------------------------------
# Chunk review statuses
# ---------------------------------------------------------------------------

class ChunkReviewStatus(str, Enum):
    CLEAN = "clean"
    ACCEPTED_WITH_RISK = "accepted_with_risk"
    SANITIZED = "sanitized"
    REMOVED = "removed"


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class VectorEventType(str, Enum):
    UPSERT_COMPLETED = "vector_db.upsert.completed"
    DELETE_REQUESTED = "vector_db.delete.requested"


# ---------------------------------------------------------------------------
# Stage update constants (files service)
# ---------------------------------------------------------------------------

class FileStage(str, Enum):
    SEMANTIC = "semantic"
    VECTOR = "vector"


STAGE_STATUS_DONE = "done"
FILES_SERVICE_NAME = "files"
FILES_UPDATE_STAGE_ACTION = "update_stage"

# Stages published to files.requests after a successful upsert
UPSERT_COMPLETION_STAGES = (FileStage.SEMANTIC, FileStage.VECTOR)


# ---------------------------------------------------------------------------
# Qdrant payload field names
# ---------------------------------------------------------------------------

PAYLOAD_FIELDS = (
    "tenant_id",
    "owner_user_id",
    "owner_admin_id",
    "file_id",
    "document_id",
    "chunk_id",
    "chunk_index",
    "chunk_version",
    "text",
    "text_preview",
    "source_name",
    "page",
    "section",
    "retrieval_allowed",
    "review_status",
    "issue_flags",
    "created_at",
)

# ---------------------------------------------------------------------------
# Qdrant indexed payload fields
# ---------------------------------------------------------------------------

from qdrant_client.models import PayloadSchemaType  # noqa: E402

INDEXED_FIELDS: dict = {
    "tenant_id": PayloadSchemaType.KEYWORD,
    "owner_user_id": PayloadSchemaType.KEYWORD,
    "owner_admin_id": PayloadSchemaType.KEYWORD,
    "file_id": PayloadSchemaType.KEYWORD,
    "document_id": PayloadSchemaType.KEYWORD,
    "chunk_version": PayloadSchemaType.INTEGER,
    "retrieval_allowed": PayloadSchemaType.BOOL,
    "review_status": PayloadSchemaType.KEYWORD,
}

# ---------------------------------------------------------------------------
# Qdrant filter-safety sets
# ---------------------------------------------------------------------------

ALLOWED_REVIEW_STATUSES: frozenset = frozenset(
    status.value for status in ChunkReviewStatus
)

SAFE_REVIEW_STATUSES: frozenset = frozenset({
    ChunkReviewStatus.CLEAN,
    ChunkReviewStatus.ACCEPTED_WITH_RISK,
    ChunkReviewStatus.SANITIZED,
})

ALLOWED_CALLER_FILTERS: frozenset = frozenset({
    "tenant_id",
    "owner_user_id",
    "owner_admin_id",
    "file_id",
    "document_id",
    "chunk_version",
    "review_status",
    "page",
    "section",
})

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

DEFAULT_TOP_K = 10
DEFAULT_COLLECTION_NAME = "rag_chunks_v1"
