"""Typed Kafka embedding-job orchestration for the embedding service.

Validates strict embedding.jobs.requested envelopes, batches eligible chunks
through the embedding model, delegates envelope construction and publishing to
EmbeddingJobPublisher, and uses shared retry + DLQ helpers for failure handling.
"""
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import ValidationError

from app.config import EmbeddingConfig
from app.embedding.interfaces import IEmbeddingModel
from app.schemas.embedding_job import (
    EmbeddingJobChunk,
    EmbeddingJobRequestedEnvelope,
    parse_model,
)
from app.services.embedding_job_publisher import EmbeddingJobPublisher
from app.services.embedding_job_tracing import EmbeddingLangSmithTracer
from app.core.logging_config import ServiceLogger
from app.messaging.embedding_kafka import EmbeddingKafkaProducer


SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.append(str(SERVICE_ROOT))

_SHARED_MODULES: Dict[str, Any] = {}


def _resolve_shared_module_path(module_name: str) -> Path:
    """Resolve a shared helper module relative to the embedding service root."""
    candidates = [
        SERVICE_ROOT / "shared" / f"{module_name}.py",
        SERVICE_ROOT.parent / "shared" / f"{module_name}.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _load_shared_module(module_name: str):
    """Load a shared module without importing shared.__init__."""
    if module_name in _SHARED_MODULES:
        return _SHARED_MODULES[module_name]

    module_path = _resolve_shared_module_path(module_name)
    if not module_path.is_file():
        raise ImportError(
            f"Unable to load shared module '{module_name}' from '{module_path}'"
        )
    spec = importlib.util.spec_from_file_location(f"embedding_shared_{module_name}", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load shared module: {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _SHARED_MODULES[module_name] = module
    return module


def _load_shared_symbol(module_name: str, symbol_name: str):
    """Load a symbol from a shared module without importing shared.__init__."""
    return getattr(_load_shared_module(module_name), symbol_name)


DeadLetterQueue = _load_shared_symbol("dlq", "DeadLetterQueue")
RetryPolicy = _load_shared_symbol("retry", "RetryPolicy")
RetryExhausted = _load_shared_symbol("retry", "RetryExhausted")


class RetryableEmbeddingJobError(Exception):
    """Retryable embedding job failure."""


class NonRetryableEmbeddingJobError(Exception):
    """Non-retryable embedding job failure."""


class EmbeddingJobService:
    """Orchestrate typed embedding-job commands into typed vector-db upserts."""

    def __init__(
        self,
        producer: EmbeddingKafkaProducer,
        embedding_model: Optional[IEmbeddingModel],
        logger: ServiceLogger,
        config: EmbeddingConfig,
        tracer: Optional[EmbeddingLangSmithTracer] = None,
    ) -> None:
        self.producer = producer
        self.embedding_model = embedding_model
        self.logger = logger
        self.config = config
        self.tracer = tracer or EmbeddingLangSmithTracer(enabled=False)
        self.batch_size = max(1, getattr(config, "embedding_max_batch_size", config.embedding_batch_size))
        self.passage_prefix = getattr(config, "embedding_passage_prefix", "") or ""
        self.dlq = DeadLetterQueue(producer=producer, service_name=config.service_name)
        self._publisher = EmbeddingJobPublisher(
            producer=producer,
            logger=logger,
            config=config,
            tracer=self.tracer,
            RetryableError=RetryableEmbeddingJobError,
        )

    def process_message(self, raw_message: Dict[str, Any]) -> bool:
        """Process one raw embedding-job envelope with retry and DLQ handling.

        Returns True when the caller should commit the Kafka offset (success or DLQ).
        """
        policy = RetryPolicy(
            max_retries=max(1, self.config.kafka_max_retries),
            base_delay=float(self.config.kafka_retry_delay),
            max_delay=max(float(self.config.kafka_retry_delay), 30.0),
            jitter=True,
        )

        try:
            policy.execute(
                self._process_job_once,
                raw_message,
                retryable_exceptions=(RetryableEmbeddingJobError,),
                on_retry=self._log_retry,
            )
            return True
        except NonRetryableEmbeddingJobError as exc:
            self._publisher.send_to_dlq(self.dlq, raw_message, exc, max(1, policy.attempt + 1))
            return True
        except RetryExhausted as exc:
            last_error = exc.last_error or RetryableEmbeddingJobError("Embedding job retries exhausted")
            self._publisher.send_to_dlq(self.dlq, raw_message, last_error, max(1, exc.attempts))
            return True

    def _process_job_once(self, raw_message: Dict[str, Any]) -> None:
        if not self.embedding_model or not self.embedding_model.is_loaded():
            raise RetryableEmbeddingJobError("Embedding model not available")

        envelope = self._parse_and_validate_job(raw_message)
        payload = envelope.payload
        eligible_chunks, skipped_chunks = self._split_chunks(payload.chunks)

        base_metadata = {
            "service": self.config.service_name,
            "request_id": envelope.request_id,
            "trace_id": envelope.trace_id,
            "correlation_id": envelope.correlation_id,
            "file_id": payload.file_id,
            "document_id": payload.document_id,
            "model_name": self.config.model_name,
            "mode": "embedding_job",
            "job_id": payload.job_id,
            "eligible_chunks": len(eligible_chunks),
            "skipped_chunks": len(skipped_chunks),
        }

        self.logger.log(
            "embedding_job:process",
            "Processing embedding job envelope",
            {
                "message_id": envelope.message_id,
                "request_id": envelope.request_id,
                "trace_id": envelope.trace_id,
                "job_id": payload.job_id,
                "file_id": payload.file_id,
                "document_id": payload.document_id,
                "requested_chunks": len(payload.chunks),
                "eligible_chunks": len(eligible_chunks),
                "skipped_chunks": len(skipped_chunks),
            },
        )

        with self.tracer.span("embedding_job.process", base_metadata):
            with self.tracer.span("embedding_job.prepare_batches", base_metadata):
                batches = [
                    eligible_chunks[i:i + self.batch_size]
                    for i in range(0, len(eligible_chunks), self.batch_size)
                ]

            if not eligible_chunks:
                completed_event = self._publisher.build_completed_envelope(
                    envelope=envelope,
                    embedded_chunks=0,
                    skipped_chunks=len(skipped_chunks),
                    batches_processed=0,
                    vector_dimensions=0,
                )
                self._publisher.publish_completed_event(completed_event, base_metadata)
                return

            vector_dimensions = 0
            batches_processed = 0

            for batch_index, batch_chunks in enumerate(batches):
                batch_metadata = {**base_metadata, "batch_index": batch_index}

                with self.tracer.span("embedding_job.embed_batch", batch_metadata):
                    try:
                        model_inputs = self._prepare_model_inputs(batch_chunks)
                        embeddings = self.embedding_model.encode_batch(
                            model_inputs,
                            batch_size=min(self.batch_size, len(batch_chunks)),
                        )
                    except Exception as exc:
                        raise RetryableEmbeddingJobError(
                            f"Embedding batch {batch_index} failed: {exc}"
                        ) from exc

                if len(embeddings) != len(batch_chunks):
                    raise NonRetryableEmbeddingJobError(
                        f"Embedding count mismatch for batch {batch_index}: "
                        f"expected {len(batch_chunks)}, got {len(embeddings)}"
                    )

                if embeddings and vector_dimensions == 0:
                    vector_dimensions = len(embeddings[0])

                with self.tracer.span("embedding_job.package_output", batch_metadata):
                    upsert_envelope = self._publisher.build_upsert_envelope(
                        envelope=envelope,
                        chunks=batch_chunks,
                        embeddings=embeddings,
                    )

                self._publisher.publish_upsert(upsert_envelope, batch_index, batch_metadata)
                batches_processed += 1

            completed_event = self._publisher.build_completed_envelope(
                envelope=envelope,
                embedded_chunks=len(eligible_chunks),
                skipped_chunks=len(skipped_chunks),
                batches_processed=batches_processed,
                vector_dimensions=vector_dimensions,
            )
            self._publisher.publish_completed_event(completed_event, base_metadata)

    def _parse_and_validate_job(self, raw_message: Dict[str, Any]) -> EmbeddingJobRequestedEnvelope:
        try:
            envelope = parse_model(EmbeddingJobRequestedEnvelope, raw_message)
        except ValidationError as exc:
            raise NonRetryableEmbeddingJobError(f"Invalid embedding job envelope: {exc}") from exc

        payload = envelope.payload
        source_names = set()
        for chunk in payload.chunks:
            if chunk.file_id != payload.file_id:
                raise NonRetryableEmbeddingJobError(
                    f"Chunk {chunk.chunk_id} file_id does not match payload file_id"
                )
            if chunk.document_id != payload.document_id:
                raise NonRetryableEmbeddingJobError(
                    f"Chunk {chunk.chunk_id} document_id does not match payload document_id"
                )
            source_names.add(chunk.source_name)

        if len(source_names) > 1:
            raise NonRetryableEmbeddingJobError(
                "All chunks in a job must share the same source_name"
            )
        return envelope

    def _split_chunks(
        self,
        chunks: Sequence[EmbeddingJobChunk],
    ) -> Tuple[List[EmbeddingJobChunk], List[EmbeddingJobChunk]]:
        eligible: List[EmbeddingJobChunk] = []
        skipped: List[EmbeddingJobChunk] = []
        for chunk in chunks:
            if chunk.retrieval_allowed and chunk.review_status != "removed":
                eligible.append(chunk)
            else:
                skipped.append(chunk)
        return eligible, skipped

    def _prepare_model_inputs(self, chunks: Sequence[EmbeddingJobChunk]) -> List[str]:
        if not self.passage_prefix:
            return [chunk.text for chunk in chunks]
        return [f"{self.passage_prefix}{chunk.text}" for chunk in chunks]

    def _log_retry(self, attempt: int, error: Exception) -> None:
        self.logger.log(
            "embedding_job:retry",
            "Retrying embedding job",
            {
                "attempt": attempt + 1,
                "error": str(error),
                "error_type": type(error).__name__,
            },
            hypothesis_id="W",
        )
