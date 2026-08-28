"""FileRepository — the public database facade for the files service.

Composes all domain mixins via multiple inheritance:

    BaseRepository          — transaction support, shared helpers
    FilesRepositoryMixin    — files collection CRUD
    TasksRepositoryMixin    — file_tasks CRUD
    ReviewRepositoryMixin   — review_cases + review_decisions CRUD
    ChunksRepositoryMixin   — file_chunks write + versioning
    AuditRepositoryMixin    — file_audit_events write + paginated read

MRO (Python reads left-to-right, BaseRepository last):

    FileRepository
      → FilesRepositoryMixin
      → TasksRepositoryMixin
      → ReviewRepositoryMixin
      → ChunksRepositoryMixin
      → AuditRepositoryMixin
      → BaseRepository

Every public method is implemented in exactly one mixin. ``FileRepository``
itself only owns ``__init__`` (wires the per-domain collections) and
``ensure_indexes`` (calls each mixin's ``_ensure_*_indexes`` method).
"""
from __future__ import annotations

from typing import Optional

from pymongo.collection import Collection

from shared.errors import DatabaseException
from app.db._audit import AuditRepositoryMixin
from app.db._base import BaseRepository
from app.db._chunks import ChunksRepositoryMixin
from app.db._files import FilesRepositoryMixin
from app.db._review import ReviewRepositoryMixin
from app.db._tasks import TasksRepositoryMixin


class FileRepository(
    FilesRepositoryMixin,
    TasksRepositoryMixin,
    ReviewRepositoryMixin,
    ChunksRepositoryMixin,
    AuditRepositoryMixin,
    BaseRepository,
):
    """Single repository facade across all file-domain MongoDB collections.

    Args:
        collection: Primary ``files`` collection (required).
        client: MongoClient used for transaction sessions. Defaults to the
            client inferred from ``collection``.
        logger: Service logger. Accepts both ``ServiceLogger`` and stdlib
            ``logging.Logger`` instances.
        file_tasks_collection: ``file_tasks`` collection.
        file_chunks_collection: ``file_chunks`` collection.
        file_review_cases_collection: ``file_review_cases`` collection.
        file_review_decisions_collection: ``file_review_decisions`` collection.
        file_audit_events_collection: ``file_audit_events`` collection.

    Collections passed as ``None`` are silently skipped during index
    creation; any method that requires a missing collection will raise
    ``DatabaseException`` at call time.
    """

    def __init__(
        self,
        collection: Collection,
        *,
        client=None,
        logger=None,
        file_tasks_collection: Optional[Collection] = None,
        file_chunks_collection: Optional[Collection] = None,
        file_review_cases_collection: Optional[Collection] = None,
        file_review_decisions_collection: Optional[Collection] = None,
        file_audit_events_collection: Optional[Collection] = None,
    ) -> None:
        super().__init__(collection, client=client, logger=logger)
        self.file_tasks_collection = file_tasks_collection
        self.file_chunks_collection = file_chunks_collection
        self.file_review_cases_collection = file_review_cases_collection
        self.file_review_decisions_collection = file_review_decisions_collection
        self.file_audit_events_collection = file_audit_events_collection

    def ensure_indexes(self) -> None:
        """Create all MongoDB indexes needed by the file-domain workflow.

        Raises:
            DatabaseException: If any index creation fails.
        """
        try:
            self._ensure_files_indexes()
            self._ensure_tasks_indexes()
            self._ensure_chunks_indexes()
            self._ensure_review_indexes()
            self._ensure_audit_indexes()
        except Exception as exc:
            raise DatabaseException(f"Failed to ensure indexes: {exc}") from exc
