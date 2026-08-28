"""Shared infrastructure for all FileHandlers mixins."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import Settings
from app.core.error_handling import ExceptionHandler
from shared.errors import ValidationError as ValidationException
from app.db.repository import FileRepository
from app.messaging.interfaces import IProducer
from app.services.file_ingestion_state_machine import FileIngestionStateMachine
from app.services.graph_types import OutboundMessage
from app.utils.common import (
    build_message_envelope,
    generate_event_id,
    utcnow,
    validate_managed_file_path,
)
from shared.auth import identity_from_context


class FileHandlerBase:
    """Shared state and helper methods used by all FileHandlers mixins."""

    def __init__(
        self,
        producer: IProducer,
        repository: FileRepository,
        logger,
        config: Settings,
    ):
        self.producer = producer
        self.repository = repository
        self.logger = logger
        self.config = config
        self.state_machine = FileIngestionStateMachine(repository, producer, logger, config)

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def _check_and_update_overall_status(self, file_id: str) -> None:
        """Mark a file complete only after all required downstream stages are done."""
        file_doc = self.repository.get_by_id(file_id)
        if not file_doc or file_doc.get("status") in {"awaiting_review", "rejected", "error"}:
            return

        stages = file_doc.get("stage", {})
        required_stages = ["extraction", "embedding", "semantic", "vector", "summary", "metadata"]
        review_done = stages.get("review", "done") == "done"
        chunking_done = stages.get("chunking", "done") == "done"
        if review_done and chunking_done and all(stages.get(stage, "waiting") == "done" for stage in required_stages):
            self.repository.update_status(file_id, "complete")

    # ------------------------------------------------------------------
    # Payload / context extraction
    # ------------------------------------------------------------------

    def _payload(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Merge legacy flat payloads with the current request envelope."""
        payload = dict(request.get("payload") or {})
        for key, value in request.items():
            if key not in {
                "payload",
                "actor",
                "reply_to",
                "stream_to",
                "correlation_id",
                "request_id",
                "trace_id",
                "message_id",
                "message_type",
                "source_service",
                "target_service",
                "timestamp",
                "success",
                "error",
                "action",
                "auth_context",
            } and key not in payload:
                payload[key] = value
        return payload

    def _actor(self, request: Dict[str, Any]) -> Dict[str, Any]:
        identity = identity_from_context()
        return {
            "actor_id": identity.user_id,
            "actor_type": identity.role,
            "display_name": identity.email or identity.user_id,
        }

    def _request_context(self, request: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        request = request or {}
        return {
            "request_id": request.get("request_id"),
            "trace_id": request.get("trace_id"),
            "correlation_id": request.get("correlation_id"),
            "source_service": request.get("source_service"),
            "target_service": request.get("target_service"),
            "reply_to": request.get("reply_to"),
            "stream_to": request.get("stream_to"),
            "action": request.get("action"),
            "auth_context": request.get("auth_context"),
        }

    def _get_file_path(self, file_id: str) -> str:
        identity = identity_from_context()
        safe_tenant = "".join(char for char in identity.tenant_id if char.isalnum() or char in {"-", "_"})
        safe_file_id = "".join(char for char in file_id if char.isalnum() or char in {"-", "_"})
        if not safe_tenant or safe_tenant != identity.tenant_id or not safe_file_id or safe_file_id != file_id:
            raise ValidationException("Invalid tenant or file identifier")
        base = Path(self.config.upload_dir).resolve()
        target = (base / safe_tenant / safe_file_id).resolve()
        if base != target and base not in target.parents:
            raise ValidationException("Invalid upload path")
        return str(target)

    def _validate_stored_file_path(self, file_id: str, file_path: str) -> str:
        identity = identity_from_context()
        try:
            return str(validate_managed_file_path(
                self.config.upload_dir,
                identity.tenant_id,
                file_id,
                file_path,
            ))
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    # ------------------------------------------------------------------
    # Messaging helpers
    # ------------------------------------------------------------------

    def _publish_messages(self, messages: List[OutboundMessage]) -> None:
        for outbound in messages:
            self.producer.send(outbound.topic, outbound.message)
        if messages:
            self.producer.flush()

    def _send_response(
        self,
        correlation_id: str,
        data: Dict[str, Any],
        *,
        request: Optional[Dict[str, Any]] = None,
        reply_topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        request_context = self._request_context(request)
        envelope = build_message_envelope(
            message_type="reply",
            action=request_context.get("action") or "reply",
            source_service=self.config.service_name,
            target_service=request_context.get("source_service") or "gateway",
            request_id=request_context.get("request_id"),
            trace_id=request_context.get("trace_id"),
            correlation_id=correlation_id,
            payload=data,
            success=True,
        )
        return envelope

    def _send_error(
        self,
        correlation_id: str,
        error_message: str,
        *,
        request: Optional[Dict[str, Any]] = None,
        reply_topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        exception = ValidationException(error_message)
        handler = ExceptionHandler(logger=self.logger)
        error_response = handler.handle(exception, "file_handlers:_send_error", {"correlation_id": correlation_id})
        request_context = self._request_context(request)
        envelope = build_message_envelope(
            message_type="reply",
            action=request_context.get("action") or "reply",
            source_service=self.config.service_name,
            target_service=request_context.get("source_service") or "gateway",
            request_id=request_context.get("request_id"),
            trace_id=request_context.get("trace_id"),
            correlation_id=correlation_id,
            payload={},
            success=False,
            error=error_response,
        )
        return envelope

    def _audit_event(
        self,
        *,
        file_doc: Dict[str, Any],
        task_id: Optional[str],
        event_type: str,
        actor: Dict[str, Any],
        reason: str,
        details: Dict[str, Any],
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "event_id": generate_event_id(),
            "file_id": file_doc["file_id"],
            "document_id": file_doc.get("document_id") or file_doc["file_id"],
            "task_id": task_id,
            "review_case_id": None,
            "decision_id": None,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "actor": actor,
            "reason": reason,
            "details": details,
            "file_ref": {
                "db": "files",
                "collection": "files",
                "file_id": file_doc["file_id"],
                "document_id": file_doc.get("document_id") or file_doc["file_id"],
                "filename": file_doc["filename"],
            },
            "created_at": utcnow(),
            **self._ownership(file_doc),
        }

    @staticmethod
    def _ownership(file_doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: file_doc[key]
            for key in ("tenant_id", "owner_user_id", "owner_admin_id")
            if file_doc.get(key) is not None
        }

    def _write_ingestion_failure_event(
        self,
        file_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        actor: Dict[str, Any],
        exc: Exception,
        *,
        review_case_id: Optional[str] = None,
    ) -> None:
        """Best-effort ingestion failure audit logging."""
        try:
            with self.repository.transaction() as session:
                event = self._audit_event(
                    file_doc=file_doc,
                    task_id=task_doc.get("task_id"),
                    event_type="graph_failed",
                    actor=actor,
                    reason="The file ingestion workflow failed.",
                    details={"error": str(exc), "error_type": type(exc).__name__},
                )
                event["review_case_id"] = review_case_id
                self.repository.insert_audit_event(event, session=session)
        except Exception:
            return
