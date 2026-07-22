"""Message handlers for file ingestion, review, and cleanup flows.

Logic is split across focused mixin modules:
  - _file_handler_base.py  → FileHandlerBase  (shared state + infrastructure)
  - _file_ingestion.py     → FileIngestionMixin  (upload, extraction)
  - _file_review.py        → FileReviewMixin     (review cases, audit trail)
  - _file_query.py         → FileQueryMixin      (list, get, summary, questions)
  - _file_update.py        → FileUpdateMixin     (fire-and-forget updates)
  - _file_delete.py        → FileDeleteMixin     (delete, rerun stage)
"""
from app.services._file_handler_base import FileHandlerBase
from app.services._file_ingestion import FileIngestionMixin
from app.services._file_review import FileReviewMixin
from app.services._file_query import FileQueryMixin
from app.services._file_update import FileUpdateMixin
from app.services._file_delete import FileDeleteMixin


class FileHandlers(
    FileIngestionMixin,
    FileReviewMixin,
    FileQueryMixin,
    FileUpdateMixin,
    FileDeleteMixin,
    FileHandlerBase,
):
    """Implement the files service request and pipeline-event surface."""
