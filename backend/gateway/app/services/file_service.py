"""File service — file upload, review, audit, and deletion via the files service."""
from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import UploadFile

from app.core.constants import FileAction, VectorDbAction, VECTOR_CLEANUP_TIMEOUT
from app.core.correlation import add_correlation_metadata
from app.services.base import BaseRPCService
from app.core.errors import ValidationError


class FileService(BaseRPCService):
    """RabbitMQ-backed facade for file ingestion and management operations."""

    async def upload_file(self, file: UploadFile) -> Dict[str, Any]:
        """Upload a file by sending base64-encoded content over RabbitMQ RPC."""
        self.logger.log(
            "file_service:upload_file",
            "File upload request received",
            {"filename": file.filename, "content_type": file.content_type},
        )

        safe_filename = os.path.basename(file.filename or "").strip()
        extension = Path(safe_filename).suffix.lower()
        content_type = (file.content_type or "application/octet-stream").lower()
        if not safe_filename or safe_filename in {".", ".."} or "\x00" in safe_filename:
            raise ValidationError("Invalid filename")
        if extension not in self.config.allowed_upload_extensions_set:
            raise ValidationError("File extension is not allowed")
        if content_type not in self.config.allowed_upload_content_types_set:
            raise ValidationError("File content type is not allowed")

        chunks = []
        total = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > self.config.max_upload_bytes:
                raise ValidationError("File exceeds the configured upload size limit")
            chunks.append(chunk)
        file_content = b"".join(chunks)
        if not file_content:
            raise ValidationError("Empty files are not allowed")
        if extension == ".pdf" and not file_content.startswith(b"%PDF-"):
            raise ValidationError("File signature does not match PDF content")
        if extension == ".docx" and not file_content.startswith(b"PK\x03\x04"):
            raise ValidationError("File signature does not match DOCX content")
        if extension in {".txt", ".md"}:
            try:
                file_content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValidationError("Text uploads must use UTF-8 encoding") from exc

        file_id = str(uuid.uuid4())

        response = await self._send_long(
            self.config.request_topics["files"],
            {
                "action": FileAction.START_FILE_INGESTION,
                "file_id": file_id,
                "document_id": file_id,
                "filename": safe_filename,
                "content_type": content_type,
                "content": base64.b64encode(file_content).decode("utf-8"),
                "size": len(file_content),
            },
        )

        self.logger.log(
            "file_service:upload_file",
            "File upload response received",
            {"filename": safe_filename, "file_id": file_id},
        )

        upload_response = dict(response)
        upload_response.setdefault("file_id", file_id)
        upload_response.setdefault("document_id", file_id)
        upload_response.setdefault("filename", safe_filename)
        upload_response.setdefault("status", "accepted")
        return add_correlation_metadata(upload_response)

    async def get_suggested_questions(self) -> Dict[str, Any]:
        """Get suggested questions from all complete files."""
        return await self._send(
            self.config.request_topics["files"],
            {"action": FileAction.GET_SUGGESTED_QUESTIONS},
        )

    async def list_files(self) -> Dict[str, Any]:
        """List all files."""
        response = await self._send(
            self.config.request_topics["files"],
            {"action": FileAction.LIST},
        )
        self.logger.log("file_service:list_files", "File list response received", {"response": response})
        return response

    async def list_own_files(self) -> Dict[str, Any]:
        """List the calling user's own files (sanitized, no review internals)."""
        return await self._send(
            self.config.request_topics["files"],
            {"action": FileAction.LIST_OWN},
        )

    async def get_file_summary(self, file_id: str) -> Dict[str, Any]:
        """Get summary for a specific file."""
        return await self._send(
            self.config.request_topics["files"],
            {"action": FileAction.GET_SUMMARY, "file_id": file_id},
        )

    async def get_review_case(self, file_id: str) -> Dict[str, Any]:
        """Get the review case for a file."""
        response = await self._send(
            self.config.request_topics["files"],
            {"action": FileAction.GET_REVIEW_CASE, "file_id": file_id},
        )
        return add_correlation_metadata(response)

    async def submit_review_decision(self, file_id: str, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a review decision for a file."""
        response = await self._send(
            self.config.request_topics["files"],
            {"action": FileAction.SUBMIT_REVIEW_DECISION, "file_id": file_id, **decision},
        )
        return add_correlation_metadata(response)

    async def get_audit_trail(
        self,
        file_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Get the audit trail for a file."""
        payload: Dict[str, Any] = {
            "action": FileAction.GET_AUDIT_TRAIL,
            "file_id": file_id,
            "limit": limit,
        }
        if cursor:
            payload["cursor"] = cursor
        response = await self._send(
            self.config.request_topics["files"],
            payload,
        )
        return add_correlation_metadata(response)

    async def delete_file(self, file_id: str) -> Dict[str, Any]:
        """Delete a file and best-effort clean up its vectors."""
        response = await self._send(
            self.config.request_topics["files"],
            {"action": FileAction.DELETE, "file_id": file_id},
        )
        if response and response.get("status") == "success":
            try:
                await self._send(
                    self.config.request_topics["vector_db"],
                    {"action": VectorDbAction.DELETE_BY_FILE_ID, "file_id": file_id},
                    timeout=VECTOR_CLEANUP_TIMEOUT,
                )
            except Exception as vec_err:
                self.logger.error(
                    "file_service:delete_file",
                    "Vector DB cleanup failed (file already deleted)",
                    vec_err,
                )
        return response

    async def rerun_stage(self, file_id: str, stage: str) -> Dict[str, Any]:
        """Re-run a processing stage for a file."""
        return await self._send(
            self.config.request_topics["files"],
            {"action": FileAction.RERUN_STAGE, "file_id": file_id, "stage": stage},
        )
