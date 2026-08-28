"""Service-wide string constants — no magic strings anywhere else."""
from enum import Enum


class EmbeddingAction(str, Enum):
    UPSERT_CHUNKS = "upsert_chunks"
    UPDATE_STAGE = "update_stage"
    COMPLETE_EXTRACTION = "complete_extraction"


class FileStage(str, Enum):
    EMBEDDING = "embedding"
    EXTRACTION = "extraction"


class FileStatus(str, Enum):
    DONE = "done"
    ERROR = "error"
