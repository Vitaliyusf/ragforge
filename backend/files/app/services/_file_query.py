"""File query request handlers (list, get, summary, questions)."""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, Optional

from app.core.errors import ValidationException


UNRESOLVED_FILE = "UNRESOLVED_FILE"
AMBIGUOUS_FILE_MATCH = "AMBIGUOUS_FILE_MATCH"
RESOLVED_FILE = "RESOLVED"


def normalized_file_label(value: str) -> str:
    """Conservatively normalize a filename without changing its path or punctuation."""
    return unicodedata.normalize("NFC", value).casefold()

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

    def handle_resolve_file_labels(
        self,
        correlation_id: str,
        request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve expected filenames inside the repository's tenant scope.

        Exact matches always take precedence over normalized matches. More than
        one candidate is reported as ambiguous; this method never picks one.
        """
        payload = self._payload(request or {})
        labels = payload.get("labels")
        if not isinstance(labels, list) or any(
            not isinstance(label, str) or not label for label in labels
        ):
            raise ValidationException("labels must be a list of non-empty strings")

        records = self.repository.get_filename_records()
        resolutions = []
        for label in dict.fromkeys(labels):
            exact = [row for row in records if row.get("filename") == label]
            candidates = exact or [
                row
                for row in records
                if isinstance(row.get("filename"), str)
                and normalized_file_label(row["filename"])
                == normalized_file_label(label)
            ]
            file_ids = list(
                dict.fromkeys(
                    str(row.get("file_id"))
                    for row in candidates
                    if row.get("file_id")
                )
            )
            status = (
                UNRESOLVED_FILE
                if not file_ids
                else RESOLVED_FILE
                if len(file_ids) == 1
                else AMBIGUOUS_FILE_MATCH
            )
            resolutions.append(
                {
                    "label": label,
                    "status": status,
                    "file_id": file_ids[0] if status == RESOLVED_FILE else None,
                    "candidate_file_ids": file_ids if status == AMBIGUOUS_FILE_MATCH else [],
                }
            )
        return self._send_response(
            correlation_id,
            {"resolutions": resolutions},
            request=request,
            reply_topic=(request or {}).get("reply_to"),
        )

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
