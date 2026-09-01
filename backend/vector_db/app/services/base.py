"""Base service class for the vector_db service.

Owns all Kafka envelope helpers, reply/event publishing, and
the shared producer abstraction. Concrete services extend this
and implement domain-specific operation methods.
"""
from abc import ABC
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from app.core.constants import (
    MessageType,
    VectorAction,
    VectorEventType,
)
from app.core.errors import InvalidVectorError
from shared.logging import ServiceLogger
from app.db.interfaces import IVectorStore
from app.messaging.interfaces import IProducer
from app.schemas.vector import KafkaReplyEnvelope
from shared.auth import attach_internal_auth_context
from shared.kafka_base import kafka_document_key


class BaseVectorService(ABC):
    """Shared Kafka envelope helpers for vector_db services.

    Subclasses receive all infrastructure dependencies through the
    constructor and use the private helpers below to send replies and
    publish events without duplicating producer/flush logic.
    """

    def __init__(
        self,
        vector_store: IVectorStore,
        producer: IProducer,
        service_logger: ServiceLogger,
        upsert_completed_topic: str,
        files_topic: str = "files.requests",
        request_topic: str = "vector_db.requests",
        upsert_requested_topic: str = "vector_db.upsert.requested",
        delete_requested_topic: str = "vector_db.delete.requested",
        service_name: str = "vector_db",
    ) -> None:
        self.vector_store = vector_store
        self.producer = producer
        self.logger = service_logger
        self.upsert_completed_topic = upsert_completed_topic
        self.files_topic = files_topic
        self.request_topic = request_topic
        self.upsert_requested_topic = upsert_requested_topic
        self.delete_requested_topic = delete_requested_topic
        self.service_name = service_name

    # ------------------------------------------------------------------
    # Producer helpers
    # ------------------------------------------------------------------

    def _send(self, topic: str, message: Dict[str, Any]) -> None:
        """Send a message without flushing (batch-safe)."""
        envelope = attach_internal_auth_context(message)
        self.producer.send(topic, envelope, key=kafka_document_key(envelope))

    def _send_and_flush(self, topic: str, message: Dict[str, Any]) -> None:
        """Send a message and immediately flush the producer."""
        envelope = attach_internal_auth_context(message)
        self.producer.send(topic, envelope, key=kafka_document_key(envelope))
        self.producer.flush()

    def _flush(self) -> None:
        """Flush pending producer messages."""
        self.producer.flush()

    # ------------------------------------------------------------------
    # Timestamp helper
    # ------------------------------------------------------------------

    def _now_iso(self) -> str:
        """Return the current UTC timestamp in ISO-8601 format."""
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Envelope inference helpers
    # ------------------------------------------------------------------

    def _infer_source_service(self, reply_to: Optional[str]) -> str:
        """Infer the caller service from a reply topic when legacy requests omit it."""
        if reply_to and "." in reply_to:
            return reply_to.split(".", 1)[0]
        return "unknown"

    def _infer_action(self, topic: str, request: Dict[str, Any]) -> str:
        """Infer the action when a legacy request omits it on dedicated topics."""
        action = request.get("action")
        if action:
            return action
        if topic == self.upsert_requested_topic:
            return VectorAction.UPSERT_CHUNKS
        if topic == self.delete_requested_topic:
            return VectorAction.DELETE_CHUNKS
        return ""

    def _infer_message_type(self, action: str) -> str:
        """Infer the canonical message type for legacy requests."""
        if action == VectorAction.SEARCH_CHUNKS:
            return MessageType.QUERY
        return MessageType.COMMAND

    # ------------------------------------------------------------------
    # Legacy payload extraction
    # ------------------------------------------------------------------

    def _extract_legacy_payload(self, action: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a flat (legacy) request shape into the canonical nested payload."""
        if action == VectorAction.SEARCH_CHUNKS:
            return {
                "query_vector": request.get("query_vector"),
                "top_k": request.get("top_k", 10),
                "filters": request.get("filters", {}),
                "include_payload": request.get("include_payload", True),
                "include_vector": request.get("include_vector", False),
            }
        if action == VectorAction.UPSERT_CHUNKS:
            return {
                "review_outcome": request.get("review_outcome", "none"),
                "target_filters": request.get("target_filters"),
                "chunks": request.get("chunks", []),
            }
        if action == VectorAction.DELETE_CHUNKS:
            return {
                "review_outcome": request.get("review_outcome", "none"),
                "filters": request.get("filters", {}),
            }
        if action == VectorAction.INITIALIZE_COLLECTION:
            return {}
        return {}

    # ------------------------------------------------------------------
    # Delete topic compatibility normalizer
    # ------------------------------------------------------------------

    def _normalize_delete_topic_request(
        self,
        request: Dict[str, Any],
        action: str,
        message_type: str,
        payload: Dict[str, Any],
    ) -> tuple[str, str, Dict[str, Any]]:
        """Accept the canonical delete command and the legacy files cleanup event shape.

        The `vector_db.delete.requested` topic receives two shapes:
        the canonical `delete_chunks` command and a compatibility event emitted by
        `files`. This normalises the event into the canonical delete payload so the
        rest of the service stays schema-first.
        """
        event_type = payload.get("event_type")
        is_cleanup_event = (
            "filters" not in payload
            and (
                action == VectorEventType.DELETE_REQUESTED
                or event_type == VectorEventType.DELETE_REQUESTED
                or message_type == MessageType.EVENT
            )
        )
        if not is_cleanup_event:
            return action, message_type, payload

        file_id = payload.get("file_id") or request.get("file_id")
        document_id = payload.get("document_id") or request.get("document_id")
        filters: Dict[str, Any] = {}
        if file_id:
            filters["file_id"] = file_id
        if document_id:
            filters["document_id"] = document_id

        return (
            VectorAction.DELETE_CHUNKS,
            MessageType.COMMAND,
            {
                "review_outcome": "delete_file",
                "filters": filters,
            },
        )

    # ------------------------------------------------------------------
    # Canonical envelope builder
    # ------------------------------------------------------------------

    def _build_envelope_context(
        self,
        topic: str,
        request: Dict[str, Any],
        action: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a canonical request envelope from canonical or flat input."""
        resolved_action = action or self._infer_action(topic, request)
        payload = request.get("payload")
        if not isinstance(payload, dict):
            payload = self._extract_legacy_payload(resolved_action, request)

        resolved_message_type = (
            request.get("message_type") or self._infer_message_type(resolved_action)
        )
        if topic == self.delete_requested_topic and isinstance(payload, dict):
            resolved_action, resolved_message_type, payload = (
                self._normalize_delete_topic_request(
                    request=request,
                    action=resolved_action,
                    message_type=resolved_message_type,
                    payload=payload,
                )
            )

        message_id = request.get("message_id") or str(uuid4())
        correlation_id = request.get("correlation_id") or message_id
        request_id = request.get("request_id") or correlation_id
        trace_id = request.get("trace_id") or request_id
        reply_to = request.get("reply_to")
        source_service = request.get("source_service") or self._infer_source_service(reply_to)
        timestamp = request.get("timestamp")
        normalized_timestamp = self._now_iso() if timestamp is None else str(timestamp)

        return {
            "message_id": message_id,
            "message_type": resolved_message_type,
            "action": resolved_action,
            "source_service": source_service,
            "target_service": request.get("target_service") or self.service_name,
            "request_id": request_id,
            "trace_id": trace_id,
            "correlation_id": correlation_id,
            "reply_to": reply_to,
            "stream_to": request.get("stream_to"),
            "timestamp": normalized_timestamp,
            "payload": payload,
        }

    def _normalize_request(self, topic: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize an incoming Kafka message to the canonical envelope."""
        if not isinstance(request, dict):
            raise InvalidVectorError("Kafka request must be an object")

        normalized = self._build_envelope_context(topic, request)
        if not normalized["action"]:
            raise InvalidVectorError("action is required")
        return normalized

    # ------------------------------------------------------------------
    # Reply senders
    # ------------------------------------------------------------------

    def _send_success_reply(
        self,
        request: Any,
        action: str,
        payload: Dict[str, Any],
    ) -> None:
        """Send a canonical success reply envelope; no-op when reply_to is absent."""
        if not request.reply_to:
            return

        reply = KafkaReplyEnvelope(
            message_id=str(uuid4()),
            message_type=MessageType.REPLY,
            action=action,
            source_service=self.service_name,
            target_service=request.source_service,
            request_id=request.request_id,
            trace_id=request.trace_id,
            correlation_id=request.correlation_id,
            timestamp=self._now_iso(),
            success=True,
            payload=payload,
        )
        self._send_and_flush(request.reply_to, reply.model_dump(exclude_none=True))

    def _send_error_reply(
        self,
        request: Dict[str, Any],
        action: str,
        error_message: str,
    ) -> None:
        """Send a canonical error reply envelope; no-op when reply_to is absent."""
        reply_to = request.get("reply_to")
        if not reply_to:
            return

        def _id() -> str:
            return str(uuid4())

        reply = KafkaReplyEnvelope(
            message_id=_id(),
            message_type=MessageType.REPLY,
            action=action,
            source_service=self.service_name,
            target_service=request.get("source_service", "unknown"),
            request_id=request.get("request_id", request.get("correlation_id", _id())),
            trace_id=request.get("trace_id", request.get("request_id", _id())),
            correlation_id=request.get("correlation_id", _id()),
            timestamp=self._now_iso(),
            success=False,
            payload={},
            error={"message": error_message},
        )
        self._send_and_flush(reply_to, reply.model_dump(exclude_none=True))
