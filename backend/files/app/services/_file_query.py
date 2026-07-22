"""File query request handlers (list, get, summary, questions)."""
from __future__ import annotations

from typing import Any, Dict, Optional

# Fields an uploader is allowed to see about their own file. Everything else
# (summary, stage, review_status, latest_review_case_id, ownership ids) is
# administrator-only.
USER_VISIBLE_FILE_FIELDS = (
    "file_id",
    "document_id",
    "filename",
    "content_type",
    "size",
    "status",
    "created_at",
    "updated_at",
)


class FileQueryMixin:
    """Handle read-only file queries."""

    def handle_list(self, correlation_id: str, request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return all files."""
        files = self.repository.get_all()
        return self._send_response(correlation_id, {"files": files}, request=request, reply_topic=(request or {}).get("reply_to"))

    def handle_list_own(self, correlation_id: str, request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return the caller's own files, stripped of admin-only review internals.

        ``get_all`` is already owner-scoped by the repository for the ``user``
        role, so this only has to narrow the projection: uploaders see the
        lifecycle status of their documents, never the review case, summary,
        or per-stage pipeline detail that belongs to their administrator.
        """
        files = [
            {key: file_doc.get(key) for key in USER_VISIBLE_FILE_FIELDS}
            for file_doc in self.repository.get_all()
        ]
        return self._send_response(correlation_id, {"files": files}, request=request, reply_topic=(request or {}).get("reply_to"))

    def handle_get_suggested_questions(self, correlation_id: str, request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return questions from all completed files."""
        questions = self.repository.get_suggested_questions_from_complete_files()
        return self._send_response(
            correlation_id,
            {"suggested_questions": questions},
            request=request,
            reply_topic=(request or {}).get("reply_to"),
        )

    def handle_get(self, correlation_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Return a file by id."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        if not file_id:
            return self._send_error(correlation_id, "file_id is required", request=request, reply_topic=request.get("reply_to"))

        file_doc = self.repository.get_by_id(file_id)
        if not file_doc:
            return self._send_error(correlation_id, "File not found", request=request, reply_topic=request.get("reply_to"))
        return self._send_response(correlation_id, {"file": file_doc}, request=request, reply_topic=request.get("reply_to"))

    def handle_get_summary(self, correlation_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Return summary data for a file."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        if not file_id:
            return self._send_error(correlation_id, "file_id is required", request=request, reply_topic=request.get("reply_to"))
        summary_data = self.repository.get_summary(file_id)
        if not summary_data:
            return self._send_error(correlation_id, "File not found", request=request, reply_topic=request.get("reply_to"))
        return self._send_response(correlation_id, summary_data, request=request, reply_topic=request.get("reply_to"))
