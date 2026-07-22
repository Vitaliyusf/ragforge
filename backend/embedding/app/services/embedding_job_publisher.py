"""Envelope builders and Kafka publish helpers for the embedding-job pipeline.

This module is intentionally separated from EmbeddingJobService so that
orchestration logic (batching, retry, validation) stays distinct from the
envelope construction and publish concerns.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

from app.schemas.embedding_job import (
    EmbeddedJobChunk,
    EmbeddingJobChunk,
    EmbeddingJobRequestedEnvelope,
    EmbeddingJobsCompletedEnvelope,
    EmbeddingJobsCompletedPayload,
    VectorDbUpsertRequestedEnvelope,
    VectorDbUpsertRequestedPayload,
    model_to_dict,
)
from app.core.constants import EmbeddingAction, FileStage, FileStatus
from app.messaging.embedding_kafka import EmbeddingKafkaProducer
from shared.auth import attach_internal_auth_context


class EmbeddingJobPublisher:
    """Build typed envelopes and publish them to the correct Kafka topics."""

    def __init__(
        self,
        producer: EmbeddingKafkaProducer,
        logger,
        config,
        tracer,
        RetryableError,
    ) -> None:
        self._producer = producer
        self._logger = logger
        self._config = config
        self._tracer = tracer
        self._RetryableError = RetryableError

    # ------------------------------------------------------------------
    # Envelope builders
    # ------------------------------------------------------------------

    def build_upsert_envelope(
        self,
        envelope: EmbeddingJobRequestedEnvelope,
        chunks: Sequence[EmbeddingJobChunk],
        embeddings: Sequence[List[float]],
    ) -> VectorDbUpsertRequestedEnvelope:
        """Build the vector_db upsert envelope for a single batch."""
        payload_chunks = [
            EmbeddedJobChunk(
                file_id=chunk.file_id,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                chunk_version=chunk.chunk_version,
                text=chunk.text,
                text_preview=chunk.text_preview,
                source_name=chunk.source_name,
                page=chunk.page,
                section=chunk.section,
                retrieval_allowed=chunk.retrieval_allowed,
                review_status=chunk.review_status,
                issue_flags=list(chunk.issue_flags),
                created_at=chunk.created_at,
                tenant_id=chunk.tenant_id,
                owner_user_id=chunk.owner_user_id,
                owner_admin_id=chunk.owner_admin_id,
                embedding=list(embedding),
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]
        return VectorDbUpsertRequestedEnvelope(
            message_id=self._generate_message_id(),
            message_type="command",
            action=EmbeddingAction.UPSERT_CHUNKS,
            source_service="embedding",
            target_service="vector_db",
            request_id=envelope.request_id,
            trace_id=envelope.trace_id,
            correlation_id=envelope.correlation_id,
            timestamp=self._utc_now_iso(),
            payload=VectorDbUpsertRequestedPayload(
                review_outcome="none",
                collection_name=self._config.vector_db_collection_name,
                chunks=payload_chunks,
            ),
        )

    def build_completed_envelope(
        self,
        envelope: EmbeddingJobRequestedEnvelope,
        embedded_chunks: int,
        skipped_chunks: int,
        batches_processed: int,
        vector_dimensions: int,
    ) -> EmbeddingJobsCompletedEnvelope:
        """Build the final embedding.jobs.completed envelope."""
        payload = envelope.payload
        return EmbeddingJobsCompletedEnvelope(
            message_id=self._generate_message_id(),
            message_type="event",
            action="embedding_job_completed",
            source_service="embedding",
            target_service="platform",
            request_id=envelope.request_id,
            trace_id=envelope.trace_id,
            correlation_id=envelope.correlation_id,
            timestamp=self._utc_now_iso(),
            payload=EmbeddingJobsCompletedPayload(
                job_id=payload.job_id,
                file_id=payload.file_id,
                document_id=payload.document_id,
                status="completed",
                requested_chunks=len(payload.chunks),
                embedded_chunks=embedded_chunks,
                skipped_chunks=skipped_chunks,
                batches_processed=batches_processed,
                model_name=self._config.model_name,
                vector_dimensions=vector_dimensions,
                completed_at=self._utc_now_iso(),
            ),
        )

    # ------------------------------------------------------------------
    # Publish helpers
    # ------------------------------------------------------------------

    def publish_upsert(
        self,
        upsert_envelope: VectorDbUpsertRequestedEnvelope,
        batch_index: int,
        batch_metadata: Dict[str, Any],
    ) -> None:
        """Publish a single upsert envelope, raising a retryable error on failure."""
        with self._tracer.span("embedding_job.publish_upsert", batch_metadata):
            try:
                self._producer.publish_upsert_requested(attach_internal_auth_context(
                    model_to_dict(upsert_envelope, exclude_none=True)
                ))
                self._producer.flush()
            except Exception as exc:
                raise self._RetryableError(
                    f"Failed to publish upsert payload for batch {batch_index}: {exc}"
                ) from exc

    def publish_completed_event(
        self,
        completed_event: EmbeddingJobsCompletedEnvelope,
        metadata: Dict[str, Any],
    ) -> None:
        """Publish the completion event and file stage update."""
        with self._tracer.span("embedding_job.publish_completed", metadata):
            try:
                self._producer.publish_job_completed(attach_internal_auth_context(
                    model_to_dict(completed_event, exclude_none=True)
                ))
                self._publish_files_stage_update(
                    request_id=completed_event.request_id,
                    trace_id=completed_event.trace_id,
                    correlation_id=completed_event.correlation_id,
                    file_id=completed_event.payload.file_id,
                    stage=FileStage.EMBEDDING,
                    status=FileStatus.DONE,
                )
                self._producer.flush()
            except Exception as exc:
                raise self._RetryableError(
                    f"Failed to publish embedding job completion: {exc}"
                ) from exc

    def _publish_files_stage_update(
        self,
        *,
        request_id: str,
        trace_id: str,
        correlation_id: str,
        file_id: str,
        stage: str,
        status: str,
    ) -> None:
        self._producer.send(
            self._config.files_topic,
            attach_internal_auth_context({
                "message_id": self._generate_message_id(),
                "message_type": "command",
                "action": EmbeddingAction.UPDATE_STAGE,
                "source_service": "embedding",
                "target_service": "files",
                "request_id": request_id,
                "trace_id": trace_id,
                "correlation_id": correlation_id,
                "timestamp": self._utc_now_iso(),
                "payload": {
                    "file_id": file_id,
                    "stage": stage,
                    "status": status,
                },
            }),
        )

    def send_to_dlq(
        self,
        dlq,
        raw_message: Dict[str, Any],
        error: Exception,
        retry_count: int,
    ) -> None:
        """Publish the original job to the DLQ."""
        payload = raw_message.get("payload", {}) if isinstance(raw_message, dict) else {}
        self._logger.log(
            "embedding_job:dlq",
            "Embedding job sent to DLQ",
            {
                "message_id": raw_message.get("message_id") if isinstance(raw_message, dict) else None,
                "request_id": raw_message.get("request_id") if isinstance(raw_message, dict) else None,
                "job_id": payload.get("job_id"),
                "file_id": payload.get("file_id"),
                "document_id": payload.get("document_id"),
                "retry_count": retry_count,
                "error": str(error),
                "error_type": type(error).__name__,
            },
            hypothesis_id="E",
        )
        dlq.send(
            original_message=raw_message,
            error=error,
            original_topic=self._config.embedding_jobs_requested_topic,
            retry_count=retry_count,
        )
        self._producer.flush()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_message_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
