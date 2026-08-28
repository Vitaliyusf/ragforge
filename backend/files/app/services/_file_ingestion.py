"""File ingestion and extraction request handlers."""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional

from app.core.errors import NotFoundException, ValidationException
from app.services.graph_types import OutboundMessage
from app.utils.common import (
    build_message_envelope,
    create_file_document,
    create_file_task_document,
    generate_file_id,
    generate_task_id,
)


class FileIngestionMixin:
    """Handle file upload and extraction lifecycle actions."""

    def handle_upload(self, correlation_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Backward-compatible alias for start_file_ingestion."""
        return self.handle_start_file_ingestion(correlation_id, request)

    def handle_start_file_ingestion(self, correlation_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Create file and task records and publish the extract command."""
        payload = self._payload(request)
        request_context = self._request_context(request)
        filename = os.path.basename(payload.get("filename") or "unknown").strip()
        if not filename or filename in {".", ".."} or "\x00" in filename or len(filename) > 255:
            raise ValidationException("Invalid filename")
        content_type = payload.get("content_type", "application/octet-stream")
        file_id = payload.get("file_id") or generate_file_id()
        document_id = payload.get("document_id") or file_id
        content_b64 = payload.get("content")
        file_path = payload.get("path", "")
        size = int(payload.get("size") or 0)

        # Accept base64 content from gateway and save to local uploads dir
        if content_b64:
            try:
                file_bytes = base64.b64decode(content_b64, validate=True)
            except (ValueError, TypeError) as exc:
                raise ValidationException("Invalid file content encoding") from exc
            if len(file_bytes) > self.config.max_upload_bytes:
                raise ValidationException("File exceeds the configured upload size limit")
            file_dir = self._get_file_path(file_id)
            os.makedirs(file_dir, exist_ok=True)
            file_path = os.path.join(file_dir, filename)
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            size = len(file_bytes)
        elif not file_path:
            raise ValidationException(
                "File content or path is required to start ingestion",
            )
        else:
            file_path = self._validate_stored_file_path(file_id, file_path)
            if not os.path.isfile(file_path):
                raise ValidationException("Managed file path does not exist")
            if os.path.getsize(file_path) > self.config.max_upload_bytes:
                raise ValidationException("File exceeds the configured upload size limit")

        file_doc = create_file_document(
            file_id,
            filename,
            file_path,
            content_type,
            size,
            document_id=document_id,
        )
        task_id = payload.get("task_id") or generate_task_id()
        task_doc = create_file_task_document(task_id, file_doc, request_context=request_context)
        file_doc["current_task_id"] = task_id
        file_doc["status"] = "started"
        file_doc["stage"]["extraction"] = "running"

        actor = self._actor(request)
        with self.repository.transaction() as session:
            self.repository.create(file_doc, session=session)
            self.repository.create_task(task_doc, session=session)
            self.repository.insert_audit_event(
                self._audit_event(
                    file_doc=file_doc,
                    task_id=task_id,
                    event_type="file_uploaded",
                    actor=actor,
                    reason="File ingestion started.",
                    details={"path": file_path},
                    from_status=None,
                    to_status="started",
                ),
                session=session,
            )

        self._publish_messages(
            [
                OutboundMessage(
                    self.config.extract_topic,
                    build_message_envelope(
                        message_type="command",
                        action="extract",
                        source_service=self.config.service_name,
                        target_service="embedding",
                        request_id=request_context.get("request_id"),
                        trace_id=request_context.get("trace_id"),
                        correlation_id=request_context.get("correlation_id"),
                        payload={
                            "file_id": file_id,
                            "document_id": document_id,
                            "task_id": task_id,
                            "path": file_path,
                            "filename": filename,
                            "content_type": content_type,
                            "size": size,
                        },
                    ),
                )
            ]
        )
        return self._send_response(
            correlation_id,
            {
                "file_id": file_id,
                "document_id": document_id,
                "task_id": task_id,
                "filename": filename,
                "size": size,
                "status": "started",
                "message": "File received and processing started",
            },
            request=request,
            reply_topic=request.get("reply_to"),
        )

    def handle_complete_extraction(self, correlation_id: Optional[str], request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Advance ingestion after extraction completes."""
        payload = self._payload(request)
        request_context = self._request_context(request)
        file_id = payload.get("file_id")
        task_id = payload.get("task_id")
        extracted_text = payload.get("extracted_text", "")
        diagnostics = payload.get("diagnostics") or {}
        if not file_id:
            raise ValidationException("file_id is required")

        file_doc = self.repository.get_by_id(file_id)
        if file_doc and not task_id:
            task_id = file_doc.get("current_task_id")
        task_doc = self.repository.get_task_by_id(task_id)
        if not file_doc or not task_doc:
            raise NotFoundException("File task not found")

        try:
            outbound = self.state_machine.handle_extraction_completion(
                file_doc=file_doc,
                task_doc=task_doc,
                extracted_text=extracted_text,
                diagnostics=diagnostics,
                actor=self._actor(request),
                request_context=request_context,
            )
        except Exception as exc:
            self._write_ingestion_failure_event(file_doc, task_doc, self._actor(request), exc)
            raise
        self._publish_messages(outbound)

        if correlation_id:
            refreshed_file = self.repository.get_by_id(file_id) or file_doc
            return self._send_response(
                correlation_id,
                {
                    "file_id": file_id,
                    "task_id": task_id,
                    "status": refreshed_file.get("status"),
                    "review_status": refreshed_file.get("review_status"),
                    "latest_review_case_id": refreshed_file.get("latest_review_case_id"),
                },
                request=request,
                reply_topic=request.get("reply_to"),
            )
        return None
