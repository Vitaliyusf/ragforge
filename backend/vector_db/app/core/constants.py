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
    GET_METRICS = "get_metrics"
    VERIFY_CHUNK_IDS = "verify_chunk_ids"


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
# Label verification
# ---------------------------------------------------------------------------

# The only payload fields an id-existence lookup may be keyed on. Anything
# else would turn `verify_chunk_ids` into a general payload query, which is
# exactly the arbitrary-scroll capability it must not become.
VERIFIABLE_ID_FIELDS: frozenset = frozenset({"chunk_id", "file_id"})

# Cap on how many ids one verification request may name, per field. A golden
# set is tens to hundreds of labels; a request naming more is not a golden
# set, and an unbounded list would let a caller scroll the collection one
# guessed id at a time in a single round trip.
MAX_VERIFY_IDS = 1000

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

DEFAULT_TOP_K = 10
DEFAULT_COLLECTION_NAME = "rag_chunks_v1"
