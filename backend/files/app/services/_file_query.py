"""File query request handlers (list, get, summary, questions)."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

from app.core.errors import ValidationException


UNRESOLVED_FILE = "UNRESOLVED_FILE"
AMBIGUOUS_FILE_MATCH = "AMBIGUOUS_FILE_MATCH"
RESOLVED_FILE = "RESOLVED"
READY_FILE = "READY"
FILE_MISSING = "FILE_MISSING"
FILE_DELETED = "FILE_DELETED"
FILE_NOT_SEARCHABLE = "FILE_NOT_SEARCHABLE"
RESOLVED_FACT = "RESOLVED"
UNRESOLVED_FACT = "UNRESOLVED_FACT"


def normalized_file_label(value: str) -> str:
    """Conservatively normalize a filename without changing its path or punctuation."""
    return unicodedata.normalize("NFC", value).casefold()


def normalized_match_text(value: str) -> str:
    """Normalize Unicode and whitespace without fuzzy or case-insensitive matching."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()

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

    def handle_resolve_chunk_labels(
        self,
        correlation_id: str,
        request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve exact expected facts to current, searchable tenant chunks.

        The response exposes identifiers and readiness only. Chunk text never
        leaves Files, and every repository query is scoped from trusted auth
        context rather than from dataset input.
        """
        payload = self._payload(request or {})
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValidationException("items must be a list")

        normalized_items: List[Dict[str, Any]] = []
        file_ids: List[str] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValidationException(f"items[{index}] must be an object")
            item_id = item.get("item_id")
            facts = item.get("facts")
            requested_files = item.get("file_ids")
            if not isinstance(item_id, str) or not item_id:
                raise ValidationException(f"items[{index}].item_id must be a non-empty string")
            if not isinstance(facts, list) or any(
                not isinstance(fact, str) or not fact.strip() for fact in facts
            ):
                raise ValidationException(f"items[{index}].facts must be a list of non-empty strings")
            if not isinstance(requested_files, list) or any(
                not isinstance(file_id, str) or not file_id for file_id in requested_files
            ):
                raise ValidationException(
                    f"items[{index}].file_ids must be a list of non-empty strings"
                )
            unique_files = list(dict.fromkeys(requested_files))
            normalized_items.append(
                {"item_id": item_id, "facts": list(dict.fromkeys(facts)), "file_ids": unique_files}
            )
            file_ids.extend(unique_files)

        unique_file_ids = list(dict.fromkeys(file_ids))
        files_by_id = {
            str(record.get("file_id")): record
            for record in self.repository.get_eval_file_records(unique_file_ids)
            if record.get("file_id")
        }
        chunks = self.repository.get_eval_chunk_records(unique_file_ids)
        latest_versions: Dict[str, int] = {}
        for chunk in chunks:
            file_id = str(chunk.get("file_id") or "")
            version = int(chunk.get("chunk_version") or 0)
            latest_versions[file_id] = max(latest_versions.get(file_id, 0), version)
        eligible_by_file: Dict[str, List[Dict[str, Any]]] = {}
        for chunk in chunks:
            if not chunk.get("retrieval_allowed", False) or chunk.get("review_status") == "removed":
                continue
            chunk_id = chunk.get("chunk_id")
            file_id = chunk.get("file_id")
            text = chunk.get("text")
            if not chunk_id or not file_id or not isinstance(text, str):
                continue
            if int(chunk.get("chunk_version") or 0) != latest_versions.get(str(file_id), 0):
                continue
            eligible_by_file.setdefault(str(file_id), []).append(chunk)

        resolutions = []
        for item in normalized_items:
            readiness = [
                self._eval_file_readiness(file_id, files_by_id.get(file_id), eligible_by_file)
                for file_id in item["file_ids"]
            ]
            searchable_ids = {
                entry["file_id"] for entry in readiness if entry["status"] == READY_FILE
            }
            candidate_chunks = [
                chunk
                for file_id in item["file_ids"]
                if file_id in searchable_ids
                for chunk in eligible_by_file.get(file_id, [])
            ]
            facts = []
            all_chunk_ids: List[str] = []
            for fact in item["facts"]:
                needle = normalized_match_text(fact)
                matches = sorted(
                    {
                        str(chunk["chunk_id"])
                        for chunk in candidate_chunks
                        if needle and needle in normalized_match_text(chunk["text"])
                    }
                )
                facts.append(
                    {
                        "fact": fact,
                        "status": RESOLVED_FACT if matches else UNRESOLVED_FACT,
                        "chunk_ids": matches,
                    }
                )
                all_chunk_ids.extend(matches)
            resolutions.append(
                {
                    "item_id": item["item_id"],
                    "files": readiness,
                    "facts": facts,
                    "chunk_ids": sorted(set(all_chunk_ids)),
                }
            )

        return self._send_response(
            correlation_id,
            {"resolutions": resolutions},
            request=request,
            reply_topic=(request or {}).get("reply_to"),
        )

    @staticmethod
    def _eval_file_readiness(
        file_id: str,
        file_record: Optional[Dict[str, Any]],
        eligible_by_file: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if file_record is None:
            status = FILE_MISSING
        elif file_record.get("status") in {"deleted", "rejected"} or file_record.get(
            "review_status"
        ) in {"removed", "rejected"}:
            status = FILE_DELETED
        elif file_record.get("status") != "complete" or not eligible_by_file.get(file_id):
            status = FILE_NOT_SEARCHABLE
        else:
            status = READY_FILE
        return {"file_id": file_id, "status": status, "searchable": status == READY_FILE}

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
