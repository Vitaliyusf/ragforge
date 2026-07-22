"""Chunk-native vector service for Qdrant and Kafka operations."""
import os
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

import numpy as np
from pydantic import ValidationError

from app.core.constants import (
    UPSERT_COMPLETION_STAGES,
    FILES_SERVICE_NAME,
    FILES_UPDATE_STAGE_ACTION,
    STAGE_STATUS_DONE,
    MessageType,
    UpsertReviewOutcome,
    VectorAction,
    VectorEventType,
)
from app.core.errors import InvalidVectorError, VectorStoreError
from app.schemas.vector import (
    DeleteChunksRequest,
    InitializeCollectionRequest,
    SearchChunksRequest,
    UpsertChunksRequest,
    UpsertCompletedEvent,
    UpsertCompletedPayload,
)
from app.services.base import BaseVectorService
from shared.auth import AuthError, ROLE_SERVICE, identity_from_context


KafkaRequest = Union[
    SearchChunksRequest,
    UpsertChunksRequest,
    DeleteChunksRequest,
    InitializeCollectionRequest,
]


class VectorService(BaseVectorService):
    """Domain service for chunk-native vector database operations.

    Inherits all Kafka envelope helpers from BaseVectorService and adds
    the four domain operations (search, upsert, delete, initialize) plus
    the Kafka message dispatcher.
    """

    # ------------------------------------------------------------------
    # Domain operations
    # ------------------------------------------------------------------

    def initialize_collection(self) -> str:
        """Ensure the active Qdrant collection and indexes exist."""
        collection_name = self.vector_store.initialize_collection()
        self.logger.log(
            "vector_service:initialize_collection",
            "Collection initialized",
            {"collection_name": collection_name},
        )
        return collection_name

    @staticmethod
    def _identity():
        required = os.getenv("INTERNAL_AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"}
        return identity_from_context(required=required)

    def _scoped_filters(self, filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        scoped = dict(filters or {})
        identity = self._identity()
        if identity is None:
            return scoped
        scoped["tenant_id"] = identity.tenant_id
        if identity.is_admin:
            scoped["owner_admin_id"] = identity.user_id
            scoped.pop("owner_user_id", None)
        elif identity.role != ROLE_SERVICE:
            scoped["owner_user_id"] = identity.user_id
            scoped.pop("owner_admin_id", None)
        return scoped

    def _owned_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        identity = self._identity()
        if identity is None:
            return [dict(chunk) for chunk in chunks]
        owned: List[Dict[str, Any]] = []
        for source in chunks:
            chunk = dict(source)
            supplied_tenant = chunk.get("tenant_id")
            if supplied_tenant and supplied_tenant != identity.tenant_id:
                raise InvalidVectorError("Cross-tenant chunk write denied")
            chunk["tenant_id"] = identity.tenant_id
            if identity.is_admin:
                if chunk.get("owner_admin_id") not in (None, identity.user_id):
                    raise InvalidVectorError("Chunk is outside the administrator scope")
                chunk["owner_admin_id"] = identity.user_id
                chunk.setdefault("owner_user_id", identity.user_id)
            elif identity.role == ROLE_SERVICE:
                if not chunk.get("owner_user_id") or not chunk.get("owner_admin_id"):
                    raise InvalidVectorError("Service chunk writes require explicit ownership")
            else:
                chunk["owner_user_id"] = identity.user_id
                chunk["owner_admin_id"] = identity.admin_id or identity.user_id
            owned.append(chunk)
        return owned

    def _require_admin_for_review(self, review_outcome: str) -> None:
        identity = self._identity()
        if review_outcome != UpsertReviewOutcome.NONE and identity is not None:
            if not (identity.is_admin or identity.role == ROLE_SERVICE):
                raise InvalidVectorError("Administrator role required for review decisions")

    def upsert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        review_outcome: str = UpsertReviewOutcome.NONE,
        target_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Upsert chunks, applying ordered review-flow behaviour where requested."""
        if not chunks:
            raise InvalidVectorError("chunks is required")

        self._require_admin_for_review(review_outcome)
        prepared_chunks = self._owned_chunks(chunks)
        deleted_count = 0

        if review_outcome == UpsertReviewOutcome.ACCEPT_AS_IS:
            for chunk in prepared_chunks:
                chunk["review_status"] = "accepted_with_risk"
        elif review_outcome == UpsertReviewOutcome.REMOVE_PROBLEMATIC_TEXT:
            if not target_filters:
                raise InvalidVectorError(
                    "target_filters is required for remove_problematic_text"
                )
            deleted_count = self.delete_chunks(target_filters)
            for chunk in prepared_chunks:
                chunk["review_status"] = "sanitized"
        elif review_outcome != UpsertReviewOutcome.NONE:
            raise InvalidVectorError(f"Unsupported review_outcome: {review_outcome}")

        try:
            upserted_count = self.vector_store.upsert_chunks(prepared_chunks)
        except AuthError:
            raise
        except ValueError as exc:
            raise InvalidVectorError(str(exc)) from exc
        except Exception as exc:
            raise VectorStoreError(f"Failed to upsert chunks: {exc}") from exc

        first_chunk = prepared_chunks[0]
        result = {
            "collection_name": self.vector_store.collection_name,
            "upserted_count": upserted_count,
            "deleted_count": deleted_count,
            "document_id": first_chunk.get("document_id"),
            "file_id": first_chunk.get("file_id"),
            "review_outcome": review_outcome,
        }
        self.logger.log("vector_service:upsert_chunks", "Chunks upserted", result)
        return result

    def search_chunks(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_payload: bool = True,
        include_vector: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search for chunks using the mandatory internal retrieval safety filter."""
        if not query_vector:
            raise InvalidVectorError("query_vector is required")

        try:
            query = np.asarray(query_vector, dtype=np.float32)
            results = self.vector_store.search_chunks(
                query_vector=query,
                top_k=top_k,
                filters=self._scoped_filters(filters),
                include_payload=include_payload,
                include_vector=include_vector,
            )
        except AuthError:
            raise
        except ValueError as exc:
            raise InvalidVectorError(str(exc)) from exc
        except Exception as exc:
            raise VectorStoreError(f"Failed to search chunks: {exc}") from exc

        self.logger.log(
            "vector_service:search_chunks",
            "Chunk search completed",
            {"top_k": top_k, "results_count": len(results)},
        )
        return results

    def delete_chunks(self, filters: Dict[str, Any]) -> int:
        """Hard delete chunks by file/document filter."""
        identity = self._identity()
        if identity is not None and not (identity.is_admin or identity.role == ROLE_SERVICE):
            raise InvalidVectorError("Administrator role required for chunk deletion")
        try:
            deleted_count = self.vector_store.delete_chunks(self._scoped_filters(filters))
        except AuthError:
            raise
        except ValueError as exc:
            raise InvalidVectorError(str(exc)) from exc
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete chunks: {exc}") from exc

        self.logger.log(
            "vector_service:delete_chunks",
            "Chunks deleted",
            {"deleted_count": deleted_count, "filters": filters},
        )
        return deleted_count

    # ------------------------------------------------------------------
    # RabbitMQ RPC dispatcher (returns reply dict)
    # ------------------------------------------------------------------

    def process_request(self, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a RabbitMQ RPC request and return the reply dict.

        The caller (lifespan handler) passes ``reply_to`` and
        ``correlation_id`` into the body via ``setdefault`` before calling
        this method.  The reply is *returned* — not sent via Kafka producer —
        so that the RabbitMQ consumer base class can publish it automatically.
        """
        raw_request = body if isinstance(body, dict) else {}
        action = raw_request.get("action", "unknown")
        # Use the dedicated request topic name as the virtual topic for
        # envelope normalisation — the actual routing is done by RabbitMQ.
        virtual_topic = self.request_topic

        self.logger.log(
            "vector_service:process_request",
            "Processing RabbitMQ RPC request",
            {
                "action": action,
                "correlation_id": raw_request.get("correlation_id"),
            },
        )

        try:
            normalized_request = self._normalize_request(virtual_topic, raw_request)
            action = normalized_request["action"]

            if action == VectorAction.SEARCH_CHUNKS:
                req = SearchChunksRequest.model_validate(normalized_request)
                results = self.search_chunks(
                    query_vector=req.payload.query_vector,
                    top_k=req.payload.top_k,
                    filters=req.payload.filters.model_dump(exclude_none=True),
                    include_payload=req.payload.include_payload,
                    include_vector=req.payload.include_vector,
                )
                return self._build_rpc_success(normalized_request, action, {"results": results})

            if action == VectorAction.UPSERT_CHUNKS:
                req = UpsertChunksRequest.model_validate(normalized_request)
                target_filters = None
                if req.payload.target_filters is not None:
                    target_filters = req.payload.target_filters.model_dump(exclude_none=True)
                result = self.upsert_chunks(
                    chunks=[chunk.model_dump() for chunk in req.payload.chunks],
                    review_outcome=req.payload.review_outcome,
                    target_filters=target_filters,
                )
                return self._build_rpc_success(normalized_request, action, result)

            if action == VectorAction.DELETE_CHUNKS:
                req = DeleteChunksRequest.model_validate(normalized_request)
                deleted_count = self.delete_chunks(
                    req.payload.filters.model_dump(exclude_none=True)
                )
                return self._build_rpc_success(
                    normalized_request,
                    action,
                    {
                        "deleted_count": deleted_count,
                        "collection_name": self.vector_store.collection_name,
                        "filters": req.payload.filters.model_dump(exclude_none=True),
                        "review_outcome": req.payload.review_outcome,
                    },
                )

            if action == VectorAction.INITIALIZE_COLLECTION:
                collection_name = self.initialize_collection()
                return self._build_rpc_success(
                    normalized_request, action, {"collection_name": collection_name}
                )

            raise InvalidVectorError(f"Unsupported action: {action}")

        except (ValidationError, InvalidVectorError, VectorStoreError) as exc:
            error_message = str(exc)
            self.logger.log(
                "vector_service:process_request",
                "RabbitMQ RPC request failed",
                {"action": action, "error": error_message},
                hypothesis_id="E",
            )
            return self._build_rpc_error(raw_request, action, error_message)

    def _build_rpc_success(
        self,
        normalized_request: Dict[str, Any],
        action: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a canonical success reply envelope for RabbitMQ RPC."""
        from uuid import uuid4
        return {
            "message_id": str(uuid4()),
            "message_type": MessageType.REPLY,
            "action": action,
            "source_service": self.service_name,
            "target_service": normalized_request.get("source_service", "unknown"),
            "request_id": normalized_request.get("request_id"),
            "trace_id": normalized_request.get("trace_id"),
            "correlation_id": normalized_request.get("correlation_id"),
            "timestamp": self._now_iso(),
            "success": True,
            "payload": payload,
        }

    def _build_rpc_error(
        self,
        raw_request: Dict[str, Any],
        action: str,
        error_message: str,
    ) -> Dict[str, Any]:
        """Build a canonical error reply envelope for RabbitMQ RPC."""
        from uuid import uuid4
        def _id() -> str:
            return str(uuid4())
        return {
            "message_id": _id(),
            "message_type": MessageType.REPLY,
            "action": action,
            "source_service": self.service_name,
            "target_service": raw_request.get("source_service", "unknown"),
            "request_id": raw_request.get("request_id", raw_request.get("correlation_id", _id())),
            "trace_id": raw_request.get("trace_id", raw_request.get("request_id", _id())),
            "correlation_id": raw_request.get("correlation_id", _id()),
            "timestamp": self._now_iso(),
            "success": False,
            "payload": {},
            "error": {"message": error_message},
        }

    # ------------------------------------------------------------------
    # Kafka message dispatcher
    # ------------------------------------------------------------------

    def process_kafka_message(self, topic: str, request: Dict[str, Any]) -> None:
        """Process a Kafka message from one of the vector_db request topics."""
        raw_request = request if isinstance(request, dict) else {}
        action = raw_request.get("action", "unknown")
        reply_to = raw_request.get("reply_to")
        normalized_request: Optional[Dict[str, Any]] = None

        self.logger.log(
            "vector_service:process_kafka_message",
            "Processing Kafka message",
            {
                "topic": topic,
                "action": action,
                "correlation_id": raw_request.get("correlation_id"),
            },
        )

        try:
            normalized_request = self._normalize_request(topic, raw_request)
            action = normalized_request["action"]
            reply_to = normalized_request.get("reply_to")

            if topic == self.upsert_requested_topic:
                self._handle_upsert_request(
                    UpsertChunksRequest.model_validate(normalized_request)
                )
                return

            if topic == self.delete_requested_topic:
                self._handle_delete_request(
                    DeleteChunksRequest.model_validate(normalized_request)
                )
                return

            if topic != self.request_topic:
                raise InvalidVectorError(f"Unsupported topic: {topic}")

            if action == VectorAction.SEARCH_CHUNKS:
                self._handle_search_request(
                    SearchChunksRequest.model_validate(normalized_request)
                )
            elif action == VectorAction.UPSERT_CHUNKS:
                self._handle_upsert_request(
                    UpsertChunksRequest.model_validate(normalized_request)
                )
            elif action == VectorAction.DELETE_CHUNKS:
                self._handle_delete_request(
                    DeleteChunksRequest.model_validate(normalized_request)
                )
            elif action == VectorAction.INITIALIZE_COLLECTION:
                self._handle_initialize_request(
                    InitializeCollectionRequest.model_validate(normalized_request)
                )
            else:
                raise InvalidVectorError(f"Unsupported action: {action}")

        except (ValidationError, InvalidVectorError, VectorStoreError) as exc:
            error_message = str(exc)
            error_context = normalized_request or self._build_envelope_context(
                topic, raw_request, action=action
            )
            self.logger.log(
                "vector_service:process_kafka_message",
                "Kafka message processing failed",
                {"topic": topic, "action": action, "error": error_message},
                hypothesis_id="E",
            )
            if reply_to:
                self._send_error_reply(error_context, action or "unknown", error_message)
            if action == VectorAction.UPSERT_CHUNKS:
                self._publish_upsert_completed(
                    request=error_context,
                    status="error",
                    review_outcome=error_context.get("payload", {}).get(
                        "review_outcome", UpsertReviewOutcome.NONE
                    ),
                    upserted_count=0,
                    deleted_count=0,
                    message="Chunk upsert failed",
                    error=error_message,
                )

    # ------------------------------------------------------------------
    # Topic-level request handlers
    # ------------------------------------------------------------------

    def _handle_search_request(self, request: SearchChunksRequest) -> None:
        results = self.search_chunks(
            query_vector=request.payload.query_vector,
            top_k=request.payload.top_k,
            filters=request.payload.filters.model_dump(exclude_none=True),
            include_payload=request.payload.include_payload,
            include_vector=request.payload.include_vector,
        )
        self._send_success_reply(
            request=request,
            action=VectorAction.SEARCH_CHUNKS,
            payload={"results": results},
        )

    def _handle_upsert_request(self, request: UpsertChunksRequest) -> None:
        target_filters = None
        if request.payload.target_filters is not None:
            target_filters = request.payload.target_filters.model_dump(exclude_none=True)

        result = self.upsert_chunks(
            chunks=[chunk.model_dump() for chunk in request.payload.chunks],
            review_outcome=request.payload.review_outcome,
            target_filters=target_filters,
        )
        self._send_success_reply(
            request=request,
            action=VectorAction.UPSERT_CHUNKS,
            payload=result,
        )
        self._publish_upsert_completed(
            request=request.model_dump(exclude_none=True),
            status="success",
            review_outcome=request.payload.review_outcome,
            upserted_count=result["upserted_count"],
            deleted_count=result["deleted_count"],
            message="Chunk upsert completed",
            document_id=result.get("document_id"),
            file_id=result.get("file_id"),
        )
        self._publish_files_stage_updates(
            request=request.model_dump(exclude_none=True),
            file_id=result.get("file_id"),
        )

    def _handle_delete_request(self, request: DeleteChunksRequest) -> None:
        deleted_count = self.delete_chunks(
            request.payload.filters.model_dump(exclude_none=True)
        )
        self._send_success_reply(
            request=request,
            action=VectorAction.DELETE_CHUNKS,
            payload={
                "deleted_count": deleted_count,
                "collection_name": self.vector_store.collection_name,
                "filters": request.payload.filters.model_dump(exclude_none=True),
                "review_outcome": request.payload.review_outcome,
            },
        )

    def _handle_initialize_request(self, request: InitializeCollectionRequest) -> None:
        collection_name = self.initialize_collection()
        self._send_success_reply(
            request=request,
            action=VectorAction.INITIALIZE_COLLECTION,
            payload={"collection_name": collection_name},
        )

    # ------------------------------------------------------------------
    # Event publishers
    # ------------------------------------------------------------------

    def _publish_upsert_completed(
        self,
        request: Dict[str, Any],
        status: str,
        review_outcome: str,
        upserted_count: int,
        deleted_count: int,
        message: str,
        document_id: Optional[str] = None,
        file_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Publish the canonical upsert completion event."""
        def _id() -> str:
            return str(uuid4())

        completed_at = self._now_iso()
        event = UpsertCompletedEvent(
            message_id=_id(),
            message_type=MessageType.EVENT,
            action=VectorAction.UPSERT_CHUNKS,
            source_service=self.service_name,
            target_service=request.get(
                "source_service",
                self._infer_source_service(request.get("reply_to")),
            ),
            request_id=request.get("request_id", request.get("correlation_id", _id())),
            trace_id=request.get("trace_id", request.get("request_id", _id())),
            correlation_id=request.get("correlation_id", _id()),
            timestamp=completed_at,
            event_type=VectorEventType.UPSERT_COMPLETED,
            payload=UpsertCompletedPayload(
                completed_at=completed_at,
                status=status,
                collection_name=self.vector_store.collection_name,
                document_id=document_id,
                file_id=file_id,
                review_outcome=review_outcome,
                upserted_count=upserted_count,
                deleted_count=deleted_count,
                message=message,
                error=error,
            ),
        )
        self._send_and_flush(
            self.upsert_completed_topic,
            event.model_dump(exclude_none=True),
        )

    def _publish_files_stage_updates(
        self,
        *,
        request: Dict[str, Any],
        file_id: Optional[str],
    ) -> None:
        """Mark vector stages as complete in the files service after upsert success."""
        if not file_id:
            return

        def _id() -> str:
            return str(uuid4())

        request_id = request.get("request_id", request.get("correlation_id", _id()))
        trace_id = request.get("trace_id", request_id)
        correlation_id = request.get("correlation_id", _id())
        timestamp = self._now_iso()

        for stage in UPSERT_COMPLETION_STAGES:
            self._send(
                self.files_topic,
                {
                    "message_id": _id(),
                    "message_type": MessageType.COMMAND,
                    "action": FILES_UPDATE_STAGE_ACTION,
                    "source_service": self.service_name,
                    "target_service": FILES_SERVICE_NAME,
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "correlation_id": correlation_id,
                    "timestamp": timestamp,
                    "payload": {
                        "file_id": file_id,
                        "stage": stage,
                        "status": STAGE_STATUS_DONE,
                    },
                },
            )
        self._flush()
