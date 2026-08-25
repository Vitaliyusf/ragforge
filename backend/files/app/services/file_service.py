"""Request handler for the files service (RabbitMQ RPC transport; Kafka for embedding pipeline)."""
import logging
import time
from typing import Dict, Any, Optional
from uuid import uuid4

from app.core.constants import FileAction
from app.core.errors import ValidationException, ExceptionHandler
from app.core.config import Settings
from app.db.repository import FileRepository
from app.messaging.interfaces import IProducer
from app.services.file_handlers import FileHandlers
from app.services.metrics_query import FileMetricsQueryService
from shared.auth import ROLE_SERVICE, identity_from_context, verify_internal_ticket_from_envelope
from shared.context import bound_context


class FileService:
    """Route inbound RabbitMQ RPC and Kafka pipeline actions to file handlers."""

    def __init__(
        self,
        producer: IProducer,
        repository: FileRepository,
        logger: logging.Logger,
        config: Settings,
    ):
        self.producer = producer
        self.config = config
        self.handlers = FileHandlers(producer, repository, logger, config)
        self.metrics_query = FileMetricsQueryService(repository, config)
        self.logger = logger
        self._exception_handler = ExceptionHandler(logger=logger)

    def _build_error_reply(self, request: Dict[str, Any], exc: Exception) -> Dict[str, Any]:
        """Build a structured error reply envelope from an exception."""
        correlation_id = request.get("correlation_id") or "unknown"
        action = request.get("action") or "reply"
        error_payload = self._exception_handler.handle(
            exc,
            location="file_service.process_request",
            context={"correlation_id": correlation_id, "action": action},
        )
        return {
            "message_id": str(uuid4()),
            "message_type": "reply",
            "action": action,
            "source_service": self.config.service_name,
            "target_service": request.get("source_service") or "gateway",
            "request_id": request.get("request_id") or correlation_id,
            "trace_id": request.get("trace_id") or correlation_id,
            "correlation_id": correlation_id,
            "timestamp": int(time.time() * 1000),
            "payload": {},
            "success": False,
            "error": error_payload,
        }

    def process_request(
        self,
        request: Dict[str, Any],
        *,
        reply_to: Optional[str] = None,
        correlation_id_override: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Dispatch one inbound request by ``action`` and return the reply dict.

        Args:
            request: Normalized or legacy-compatible request payload, exactly
                as signed by the sender (do not pre-merge transport metadata
                into it — see ``reply_to``/``correlation_id_override``).
            reply_to: RabbitMQ reply queue name to merge into the request
                (as a default) once the ticket has been verified against the
                unmodified envelope. ``None`` for transports with no reply.
            correlation_id_override: RabbitMQ correlation id to merge into
                the request (as a default) once verified, for requests that
                did not already carry their own ``correlation_id``.

        Returns:
            A reply envelope dict on both success and error paths.
            Returns ``None`` only for fire-and-forget actions that have no
            caller waiting for a reply (UPDATE_STAGE, UPDATE_SUMMARY,
            UPDATE_METADATA, UPDATE_SUGGESTED_QUESTIONS).
        """
        action = request.get("action", "")

        try:
            # Verify against the envelope exactly as signed, before any
            # transport-layer defaults (reply_to/correlation_id) are merged
            # in below — mutating first would change the digest the ticket
            # is bound to and make a validly-signed request fail auth.
            identity = verify_internal_ticket_from_envelope(request)

            if reply_to is not None or correlation_id_override is not None:
                request = dict(request)
                if reply_to is not None:
                    request.setdefault("reply_to", reply_to)
                if correlation_id_override is not None:
                    request.setdefault("correlation_id", correlation_id_override)

            correlation_id = request.get("correlation_id")
            context = identity.to_dict() if identity is not None else {}
            context.update({
                "request_id": request.get("request_id"),
                "trace_id": request.get("trace_id"),
                "correlation_id": correlation_id,
                "action": action,
            })
            with bound_context(**context):
                self.logger.info(
                    f"Processing {action} request",
                    extra={"correlation_id": correlation_id, "action": action},
                )
                self._authorize_action(action)
                if action == FileAction.UPLOAD:
                    return self.handlers.handle_upload(correlation_id, request)
                elif action == FileAction.START_FILE_INGESTION:
                    return self.handlers.handle_start_file_ingestion(correlation_id, request)
                elif action == FileAction.COMPLETE_EXTRACTION:
                    return self.handlers.handle_complete_extraction(correlation_id, request)
                elif action == FileAction.LIST:
                    return self.handlers.handle_list(correlation_id, request)
                elif action == FileAction.LIST_OWN:
                    return self.handlers.handle_list_own(correlation_id, request)
                elif action == FileAction.GET_SUGGESTED_QUESTIONS:
                    return self.handlers.handle_get_suggested_questions(correlation_id, request)
                elif action == FileAction.GET:
                    return self.handlers.handle_get(correlation_id, request)
                elif action == FileAction.GET_REVIEW_CASE:
                    return self.handlers.handle_get_review_case(correlation_id, request)
                elif action == FileAction.SUBMIT_REVIEW_DECISION:
                    return self.handlers.handle_submit_review_decision(correlation_id, request)
                elif action == FileAction.GET_AUDIT_TRAIL:
                    return self.handlers.handle_get_audit_trail(correlation_id, request)
                elif action == FileAction.UPDATE_STAGE:
                    self.handlers.handle_update_stage(request)
                    return None
                elif action == FileAction.UPDATE_SUMMARY:
                    self.handlers.handle_update_summary(request)
                    return None
                elif action == FileAction.UPDATE_METADATA:
                    self.handlers.handle_update_metadata(request)
                    return None
                elif action == FileAction.UPDATE_SUGGESTED_QUESTIONS:
                    self.handlers.handle_update_suggested_questions(request)
                    return None
                elif action == FileAction.GET_SUMMARY:
                    return self.handlers.handle_get_summary(correlation_id, request)
                elif action == FileAction.DELETE:
                    return self.handlers.handle_delete(correlation_id, request)
                elif action == FileAction.RERUN_STAGE:
                    return self.handlers.handle_rerun_stage(correlation_id, request)
                elif action == FileAction.GET_METRICS:
                    return self.metrics_query.handle_get_metrics(correlation_id, request)
                return self._build_error_reply(request, ValidationException(f"Unknown action: {action}"))
        except Exception as exc:
            return self._build_error_reply(request, exc)

    @staticmethod
    def _authorize_action(action: str) -> None:
        identity = identity_from_context()
        admin_actions = {
            FileAction.LIST,
            FileAction.GET,
            FileAction.GET_REVIEW_CASE,
            FileAction.SUBMIT_REVIEW_DECISION,
            FileAction.GET_AUDIT_TRAIL,
            FileAction.GET_SUMMARY,
            FileAction.DELETE,
            FileAction.RERUN_STAGE,
            FileAction.GET_METRICS,
        }
        if action in admin_actions and not (identity.is_admin or identity.role == ROLE_SERVICE):
            raise ValidationException("Administrator role required")

    def process_request_with_reply(
        self,
        body: dict,
        reply_to: str,
        correlation_id: str,
    ) -> Optional[dict]:
        """Entry point for RabbitMQ consumer. Returns reply dict, or None for fire-and-forget.

        Injects ``reply_to`` and ``correlation_id`` from the RabbitMQ message
        envelope into the body so that existing handler logic (which reads
        ``request.get("reply_to")``) routes replies correctly, then delegates
        to :meth:`process_request`.

        Returns the reply envelope dict on both success and structured-error paths.
        Returns ``None`` only for fire-and-forget update actions that have no
        caller waiting for a reply.
        """
        return self.process_request(
            body,
            reply_to=reply_to,
            correlation_id_override=correlation_id,
        )
