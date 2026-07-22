"""File deletion and stage-rerun request handlers."""
from __future__ import annotations

import os
from typing import Any, Dict

from app.services.file_ingestion_graph import OutboundMessage
from app.utils.common import build_message_envelope, generate_event_id, utcnow


class FileDeleteMixin:
    """Handle file deletion and stage-rerun actions."""

    def handle_delete(self, correlation_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a file record and request downstream vector cleanup."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        if not file_id:
            return self._send_error(correlation_id, "file_id is required", request=request, reply_topic=request.get("reply_to"))

        file_doc = self.repository.get_by_id(file_id)
        if not file_doc:
            return self._send_error(correlation_id, "File not found", request=request, reply_topic=request.get("reply_to"))

        stored_path = self._validate_stored_file_path(file_id, file_doc["path"]) if file_doc.get("path") else None
        if stored_path and os.path.exists(stored_path):
            try:
                os.remove(stored_path)
            except OSError:
                pass

        actor = self._actor(request)
        with self.repository.transaction() as session:
            deleted_chunks = self.repository.delete_chunks_for_file(file_id, session=session)
            self.repository.delete(file_id, session=session)
            self.repository.insert_audit_event(
                self._audit_event(
                    file_doc=file_doc,
                    task_id=file_doc.get("current_task_id"),
                    event_type="vector_delete_requested",
                    actor=actor,
                    reason="Vector cleanup requested by explicit delete flow.",
                    details={"reason": "explicit_delete"},
                ),
                session=session,
            )
            self.repository.insert_audit_event(
                self._audit_event(
                    file_doc=file_doc,
                    task_id=file_doc.get("current_task_id"),
                    event_type="cleanup_completed",
                    actor=actor,
                    reason="File deleted through legacy delete flow.",
                    details={"deleted_chunks": deleted_chunks, "reason": "explicit_delete"},
                ),
                session=session,
            )

        self._publish_messages(
            [
                OutboundMessage(
                    self.config.vector_db_delete_topic,
                    build_message_envelope(
                        message_type="event",
                        action="vector_db.delete.requested",
                        source_service=self.config.service_name,
                        target_service="vector_db",
                        request_id=request.get("request_id"),
                        trace_id=request.get("trace_id"),
                        correlation_id=correlation_id,
                        payload={
                            "event_id": generate_event_id(),
                            "event_type": "vector_db.delete.requested",
                            "file_id": file_doc["file_id"],
                            "document_id": file_doc.get("document_id") or file_doc["file_id"],
                            "task_id": file_doc.get("current_task_id"),
                            "reason": "explicit_delete",
                            "delete_chunks": True,
                            "delete_vectors": True,
                            "created_at": utcnow().isoformat(),
                        },
                    ),
                )
            ]
        )
        return self._send_response(
            correlation_id,
            {"status": "success", "message": "File deleted successfully"},
            request=request,
            reply_topic=request.get("reply_to"),
        )

    def handle_rerun_stage(self, correlation_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Reset a stage and retrigger extraction when supported."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        stage_name = payload.get("stage")
        if not file_id or not stage_name:
            return self._send_error(correlation_id, "file_id and stage are required", request=request, reply_topic=request.get("reply_to"))

        file_doc = self.repository.get_by_id(file_id)
        if not file_doc:
            return self._send_error(correlation_id, "File not found", request=request, reply_topic=request.get("reply_to"))

        if not self.repository.update_stage(file_id, stage_name, "waiting"):
            return self._send_error(correlation_id, "Failed to update stage", request=request, reply_topic=request.get("reply_to"))

        if stage_name == "extraction":
            request_context = self._request_context(request)
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
                                "document_id": file_doc.get("document_id") or file_id,
                                "task_id": file_doc.get("current_task_id"),
                                "path": file_doc.get("path"),
                                "filename": file_doc.get("filename", "unknown"),
                                "content_type": file_doc.get("content_type", "application/octet-stream"),
                                "size": file_doc.get("size"),
                            },
                        ),
                    )
                ]
            )

        return self._send_response(
            correlation_id,
            {
                "status": "success",
                "message": f"Stage {stage_name} reset and triggered",
                "file_id": file_id,
                "stage": stage_name,
            },
            request=request,
            reply_topic=request.get("reply_to"),
        )
