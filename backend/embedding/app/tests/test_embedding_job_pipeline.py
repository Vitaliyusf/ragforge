"""Tests for the envelope-based Kafka embedding job pipeline."""
from contextlib import contextmanager
import os
import tempfile
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.embedding.interfaces import IEmbeddingModel
from app.services.embedding_job_service import EmbeddingJobService
from app.services.embedding_job_tracing import EmbeddingLangSmithTracer
from app.services.embedding_job_worker import EmbeddingJobConsumerWorker
from app.services.embedding_handler import QueryEmbeddingHandler
from app.services.extraction_handler import ExtractionHandler
from app.services.inference_scheduler import create_scheduler
from app.messaging.embedding_kafka import EmbeddingKafkaConsumer, EmbeddingKafkaProducer


class RecordingProducer:
    """Simple in-memory producer for tests."""

    def __init__(self):
        self.messages = []
        self.keys = []
        self.flush_count = 0
        self.failures = {}

    def send(self, topic, message, key=None):
        failures = self.failures.get(topic, [])
        if failures:
            error = failures.pop(0)
            raise error
        self.messages.append((topic, message))
        self.keys.append(key)

    def flush(self):
        self.flush_count += 1

    def is_connected(self):
        return True


class RecordingLogger:
    """Capture structured logs during tests."""

    def __init__(self):
        self.entries = []

    def log(self, location, message, data=None, hypothesis_id="A"):
        self.entries.append(
            {
                "location": location,
                "message": message,
                "data": data or {},
                "hypothesis_id": hypothesis_id,
            }
        )


class FakeEmbeddingModel(IEmbeddingModel):
    """Deterministic embedding model for tests."""

    def __init__(self, responses=None, failures=None):
        self.responses = list(responses or [])
        self.failures = list(failures or [])
        self.calls = []

    def encode(self, text: str):
        return [1.0]

    def encode_batch(self, texts, batch_size=32):
        self.calls.append({"texts": list(texts), "batch_size": batch_size})
        if self.failures:
            error = self.failures.pop(0)
            raise error
        if self.responses:
            return self.responses.pop(0)
        return [[float(index), float(index) + 0.5] for index, _ in enumerate(texts)]

    def is_loaded(self):
        return True


class CommitTrackingConsumer:
    """Minimal commit-tracking consumer."""

    def __init__(self):
        self.commit_count = 0

    def commit(self):
        self.commit_count += 1


class StubJobService:
    """Simple stub for worker commit tests."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def process_message(self, message):
        if self.error is not None:
            raise self.error
        return self.result


class RecordingTraceFactory:
    """Capture LangSmith span creation for assertions."""

    def __init__(self):
        self.calls = []

    @contextmanager
    def __call__(self, name=None, **kwargs):
        self.calls.append({"name": name, **kwargs})
        yield


def make_config(**overrides):
    """Create a lightweight config object for tests."""

    base = {
        "service_name": "embedding",
        "kafka_max_retries": 2,
        "kafka_retry_delay": 0,
        "embedding_max_batch_size": 2,
        "embedding_batch_size": 2,
        "embedding_query_prefix": "query: ",
        "embedding_passage_prefix": "passage: ",
        "model_name": "intfloat/multilingual-e5-small",
        "vector_db_collection_name": "rag_chunks_v1",
        "embedding_jobs_requested_topic": "embedding.jobs.requested",
        "vector_db_upsert_requested_topic": "vector_db.upsert.requested",
        "embedding_jobs_completed_topic": "embedding.jobs.completed",
        "files_topic": "files.requests",
        "embedding_consumer_group": "embedding-test-group",
        "kafka_bootstrap_servers": "localhost:9092",
        "kafka_consumer_timeout_ms": 1000,
        "kafka_api_version": (0, 10, 1),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_chunk(index, **overrides):
    """Create a valid chunk payload."""

    chunk = {
        "file_id": "file-1",
        "document_id": "doc-1",
        "chunk_id": f"chunk-{index}",
        "chunk_index": index,
        "chunk_version": 1,
        "text": f"Chunk text {index}",
        "text_preview": f"Chunk preview {index}",
        "source_name": "source.pdf",
        "page": index + 1,
        "section": f"Section {index}",
        "retrieval_allowed": True,
        "review_status": "clean",
        "issue_flags": [],
        "created_at": "2026-03-17T10:00:00Z",
    }
    chunk.update(overrides)
    return chunk


def make_job(chunks=None, **overrides):
    """Create a valid embedding job envelope."""

    job = {
        "message_id": "msg-1",
        "message_type": "command",
        "action": "process_embedding_job",
        "source_service": "files",
        "target_service": "embedding",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "timestamp": "2026-03-17T10:00:00Z",
        "payload": {
            "job_id": "job-1",
            "file_id": "file-1",
            "document_id": "doc-1",
            "requested_at": "2026-03-17T10:00:00Z",
            "chunks": chunks if chunks is not None else [make_chunk(0), make_chunk(1)],
        },
    }
    job.update(overrides)
    return job


_ACTIVE_SCHEDULERS = []


@pytest.fixture(autouse=True)
def _shutdown_schedulers():
    """Every scheduler a test builds owns a worker thread; stop them all."""

    yield
    while _ACTIVE_SCHEDULERS:
        _ACTIVE_SCHEDULERS.pop().shutdown()


def build_scheduler(model, config):
    """Start one inference scheduler for the duration of the test."""

    scheduler = create_scheduler(model, config).start()
    _ACTIVE_SCHEDULERS.append(scheduler)
    return scheduler


def build_service(config=None, model=None, tracer=None):
    """Construct the service under test."""

    config = config or make_config()
    base_producer = RecordingProducer()
    producer = EmbeddingKafkaProducer(
        base_producer,
        config.vector_db_upsert_requested_topic,
        config.embedding_jobs_completed_topic,
    )
    logger = RecordingLogger()
    service = EmbeddingJobService(
        producer=producer,
        scheduler=build_scheduler(model or FakeEmbeddingModel(), config),
        logger=logger,
        config=config,
        tracer=tracer or EmbeddingLangSmithTracer(enabled=False),
    )
    return service, base_producer, logger


def test_process_message_batches_and_preserves_order():
    """Eligible chunks are batched in order and publish exact envelope shapes."""

    chunks = [
        make_chunk(0),
        make_chunk(1),
        make_chunk(2, retrieval_allowed=False),
        make_chunk(3),
    ]
    service, producer, _ = build_service()

    assert service.process_message(make_job(chunks=chunks)) is True

    upserts = [
        message
        for topic, message in producer.messages
        if topic == "vector_db.upsert.requested"
    ]
    completions = [
        message
        for topic, message in producer.messages
        if topic == "embedding.jobs.completed"
    ]

    assert len(upserts) == 2
    assert len(completions) == 1
    assert producer.keys == ["doc-1", "doc-1", "doc-1", "file-1"]

    first_upsert = upserts[0]
    assert first_upsert["message_type"] == "command"
    assert first_upsert["action"] == "upsert_chunks"
    assert first_upsert["source_service"] == "embedding"
    assert first_upsert["target_service"] == "vector_db"
    assert first_upsert["request_id"] == "req-1"
    assert first_upsert["trace_id"] == "trace-1"
    assert first_upsert["correlation_id"] == "corr-1"
    assert "message_id" in first_upsert
    assert "timestamp" in first_upsert
    assert "reply_to" not in first_upsert

    payload = first_upsert["payload"]
    assert payload["review_outcome"] == "none"
    assert payload["collection_name"] == "rag_chunks_v1"
    assert [chunk["chunk_id"] for chunk in payload["chunks"]] == ["chunk-0", "chunk-1"]
    assert [chunk["chunk_id"] for chunk in upserts[1]["payload"]["chunks"]] == ["chunk-3"]
    assert payload["chunks"][0]["text"] == "Chunk text 0"
    assert "embedding" in payload["chunks"][0]

    completion = completions[0]
    assert completion["message_type"] == "event"
    assert completion["action"] == "embedding_job_completed"
    assert completion["target_service"] == "platform"
    assert completion["request_id"] == "req-1"
    completion_payload = completion["payload"]
    assert completion_payload["status"] == "completed"
    assert completion_payload["requested_chunks"] == 4
    assert completion_payload["embedded_chunks"] == 3
    assert completion_payload["skipped_chunks"] == 1
    assert completion_payload["batches_processed"] == 2
    assert completion_payload["vector_dimensions"] == 2


def test_process_message_zero_eligible_chunks_only_publishes_completion():
    """Zero eligible chunks should skip upserts and still complete the job."""

    chunks = [
        make_chunk(0, retrieval_allowed=False),
        make_chunk(1, review_status="removed"),
    ]
    service, producer, _ = build_service()

    assert service.process_message(make_job(chunks=chunks)) is True

    assert [
        topic for topic, _ in producer.messages if topic == "vector_db.upsert.requested"
    ] == []
    completion = [
        message
        for topic, message in producer.messages
        if topic == "embedding.jobs.completed"
    ][0]["payload"]
    assert completion["embedded_chunks"] == 0
    assert completion["skipped_chunks"] == 2
    assert completion["batches_processed"] == 0


def test_prefix_applies_only_to_model_inputs():
    """Prefix should affect model input only, not the stored outbound text."""

    model = FakeEmbeddingModel()
    service, producer, _ = build_service(model=model)

    service.process_message(make_job(chunks=[make_chunk(0)]))

    assert model.calls[0]["texts"] == ["passage: Chunk text 0"]
    upsert = [
        message
        for topic, message in producer.messages
        if topic == "vector_db.upsert.requested"
    ][0]
    assert upsert["payload"]["chunks"][0]["text"] == "Chunk text 0"
    assert upsert["payload"]["chunks"][0]["text_preview"] == "Chunk preview 0"


def test_missing_required_envelope_fields_go_to_dlq_before_model_call():
    """Invalid envelopes should fail before any embedding call."""

    invalid_job = make_job()
    invalid_job.pop("message_id")
    model = FakeEmbeddingModel()
    service, producer, _ = build_service(model=model)

    assert service.process_message(invalid_job) is True
    assert model.calls == []

    dlq_messages = [message for topic, message in producer.messages if topic == "embedding_dlq"]
    assert len(dlq_messages) == 1
    assert dlq_messages[0]["original_message"]["request_id"] == "req-1"
    assert not [
        topic for topic, _ in producer.messages if topic == "embedding.jobs.completed"
    ]


def test_invalid_review_status_goes_to_dlq_before_model_call():
    """Non-platform review statuses should be rejected by schema validation."""

    model = FakeEmbeddingModel()
    service, producer, _ = build_service(model=model)

    assert service.process_message(make_job(chunks=[make_chunk(0, review_status="approved")])) is True
    assert model.calls == []

    dlq_messages = [message for topic, message in producer.messages if topic == "embedding_dlq"]
    assert len(dlq_messages) == 1
    assert "review_status" in dlq_messages[0]["error"]["message"]


def test_invalid_chunk_identifiers_go_to_dlq_before_model_call():
    """Chunk/job identifier mismatches should fail before any embedding call."""

    bad_chunk = make_chunk(0, file_id="different-file")
    model = FakeEmbeddingModel()
    service, producer, _ = build_service(model=model)

    assert service.process_message(make_job(chunks=[bad_chunk])) is True
    assert model.calls == []

    dlq_messages = [message for topic, message in producer.messages if topic == "embedding_dlq"]
    assert len(dlq_messages) == 1
    assert dlq_messages[0]["original_message"]["payload"]["job_id"] == "job-1"
    assert not [
        topic for topic, _ in producer.messages if topic == "embedding.jobs.completed"
    ]


def test_embedding_count_mismatch_sends_to_dlq():
    """Embedding count mismatches are treated as non-retryable failures."""

    model = FakeEmbeddingModel(responses=[[[1.0, 2.0]]])
    service, producer, _ = build_service(model=model)

    assert service.process_message(make_job()) is True

    dlq_messages = [message for topic, message in producer.messages if topic == "embedding_dlq"]
    assert len(dlq_messages) == 1
    assert "Embedding count mismatch" in dlq_messages[0]["error"]["message"]
    assert not [
        topic for topic, _ in producer.messages if topic == "embedding.jobs.completed"
    ]


def test_transient_model_failure_retries_then_succeeds():
    """Retryable model failures should retry and then complete successfully."""

    model = FakeEmbeddingModel(failures=[RuntimeError("temporary failure")])
    service, producer, logger = build_service(model=model)

    assert service.process_message(make_job(chunks=[make_chunk(0)])) is True
    assert len(model.calls) == 2
    assert any(entry["location"] == "embedding_job:retry" for entry in logger.entries)
    assert len([topic for topic, _ in producer.messages if topic == "embedding.jobs.completed"]) == 1


def test_retry_exhaustion_sends_retryable_failure_to_dlq():
    """Permanent retryable failures should exhaust retries and route to DLQ."""

    model = FakeEmbeddingModel(failures=[RuntimeError("still failing"), RuntimeError("still failing")])
    service, producer, logger = build_service(model=model)

    assert service.process_message(make_job(chunks=[make_chunk(0)])) is True

    dlq_messages = [message for topic, message in producer.messages if topic == "embedding_dlq"]
    assert len(dlq_messages) == 1
    assert dlq_messages[0]["retry_count"] == 2
    assert any(entry["location"] == "embedding_job:retry" for entry in logger.entries)
    assert not [
        topic for topic, _ in producer.messages if topic == "embedding.jobs.completed"
    ]


def test_tracing_spans_are_emitted_with_platform_metadata_when_enabled():
    """Enabled tracing should wrap expected phases and include baseline metadata."""

    trace_factory = RecordingTraceFactory()
    tracer = EmbeddingLangSmithTracer(
        enabled=True,
        project="test-project",
        trace_factory=trace_factory,
    )
    service, _, _ = build_service(tracer=tracer)

    service.process_message(make_job(chunks=[make_chunk(0), make_chunk(1)]))

    assert [call["name"] for call in trace_factory.calls] == [
        "embedding_job.process",
        "embedding_job.prepare_batches",
        "embedding_job.embed_batch",
        "embedding_job.package_output",
        "embedding_job.publish_upsert",
        "embedding_job.publish_completed",
    ]
    first_metadata = trace_factory.calls[0]["metadata"]
    assert first_metadata["service"] == "embedding"
    assert first_metadata["request_id"] == "req-1"
    assert first_metadata["trace_id"] == "trace-1"
    assert first_metadata["correlation_id"] == "corr-1"
    assert first_metadata["mode"] == "embedding_job"


def test_tracing_noops_when_disabled():
    """Disabled tracing should be safe and side-effect free."""

    tracer = EmbeddingLangSmithTracer(enabled=False)
    with tracer.span("embedding_job.process", {"job_id": "job-1"}):
        assert True


def test_embedding_job_completion_marks_embedding_stage_done():
    """Successful typed jobs should notify files that embedding finished."""

    service, producer, _ = build_service()

    service.process_message(make_job(chunks=[make_chunk(0)]))

    stage_updates = [message for topic, message in producer.messages if topic == "files.requests"]
    assert len(stage_updates) == 1
    assert stage_updates[0]["message_type"] == "command"
    assert stage_updates[0]["action"] == "update_stage"
    assert stage_updates[0]["payload"] == {
        "file_id": "file-1",
        "stage": "embedding",
        "status": "done",
    }


def test_worker_commits_after_success_and_dlq():
    """Worker should commit after both successful processing and DLQ handling."""

    success_consumer = CommitTrackingConsumer()
    success_worker = EmbeddingJobConsumerWorker(
        success_consumer,
        StubJobService(result=True),
        RecordingLogger(),
    )
    assert success_worker.handle_message(make_job()) is True
    assert success_consumer.commit_count == 1

    mismatch_model = FakeEmbeddingModel(responses=[[[1.0, 2.0]]])
    real_service, _, _ = build_service(model=mismatch_model)
    dlq_consumer = CommitTrackingConsumer()
    dlq_worker = EmbeddingJobConsumerWorker(dlq_consumer, real_service, RecordingLogger())
    assert dlq_worker.handle_message(make_job()) is True
    assert dlq_consumer.commit_count == 1


def test_extraction_handler_publishes_complete_extraction_for_typed_requests():
    """The extract lane should callback into files with complete_extraction."""

    class FakeExtractor:
        def extract(self, file_obj, filename):
            if hasattr(file_obj, "read"):
                return file_obj.read().decode("utf-8")
            return Path(file_obj).read_text(encoding="utf-8")

    producer = RecordingProducer()
    logger = RecordingLogger()
    temp_dir = str(Path(__file__).parent)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        dir=temp_dir,
        delete=False,
        encoding="utf-8",
    ) as handle:
        handle.write("typed extraction body")
        request_path = handle.name
    handler = ExtractionHandler(
        producer=producer,
        extractors=[FakeExtractor()],
        logger=logger,
        files_topic="files.requests",
        summary_topic="summary_requests",
        metadata_topic="metadata_requests",
        config=make_config(),
    )
    handler._get_extractor = lambda filename: FakeExtractor()

    try:
        handler.process_request(
            {
                "message_id": "msg-1",
                "message_type": "command",
                "action": "extract",
                "source_service": "files",
                "target_service": "embedding",
                "request_id": "req-1",
                "trace_id": "trace-1",
                "correlation_id": "corr-1",
                "payload": {
                    "file_id": "file-1",
                    "document_id": "doc-1",
                    "task_id": "task-1",
                    "path": request_path,
                    "filename": "sample.txt",
                },
            }
        )
    finally:
        os.remove(request_path)

    complete_messages = [
        message
        for topic, message in producer.messages
        if topic == "files.requests" and message.get("action") == "complete_extraction"
    ]
    assert len(complete_messages) == 1
    assert complete_messages[0]["message_type"] == "command"
    assert complete_messages[0]["payload"]["file_id"] == "file-1"
    assert complete_messages[0]["payload"]["task_id"] == "task-1"
    assert complete_messages[0]["payload"]["extracted_text"] == "typed extraction body"


def test_worker_does_not_commit_when_processing_raises():
    """Unexpected exceptions should prevent the manual commit."""

    consumer = CommitTrackingConsumer()
    worker = EmbeddingJobConsumerWorker(
        consumer,
        StubJobService(error=RuntimeError("boom")),
        RecordingLogger(),
    )

    with pytest.raises(RuntimeError):
        worker.handle_message(make_job())

    assert consumer.commit_count == 0


def test_query_embedding_handler_embeds_one_prefixed_query():
    """The RPC boundary must never chunk or route queries through passage code."""

    logger = RecordingLogger()
    model = FakeEmbeddingModel(responses=[[[0.1, 0.2, 0.3]]])
    config = make_config()
    handler = QueryEmbeddingHandler(
        scheduler=build_scheduler(model, config),
        logger=logger,
        config=config,
    )

    reply = handler.process_request_with_reply(
        {
            "message_type": "query",
            "action": "embed",
            "correlation_id": "corr-1",
            "payload": {"text": "hello world"},
        },
        "rag.replies",
        "corr-1",
    )

    assert reply == {
        "correlation_id": "corr-1",
        "data": {"embedding": [0.1, 0.2, 0.3]},
    }
    assert model.calls == [{"texts": ["query: hello world"], "batch_size": 1}]


def test_consumer_commit_delegates_to_raw_kafka_consumer():
    """EmbeddingKafkaConsumer.commit delegates to the underlying Kafka client."""

    config = make_config()
    consumer = EmbeddingKafkaConsumer(config)
    raw_consumer = CommitTrackingConsumer()
    consumer._consumer = raw_consumer

    consumer.commit()

    assert raw_consumer.commit_count == 1
