"""Shared fakes, envelope builders and fixtures for `vector_db` tests.

Cross-domain on purpose: tenant-scope, Qdrant-adapter, message-contract and
compatibility lanes all drive the real service against these doubles.
Fixtures are re-exported by app/tests/conftest.py.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shared.logging import ServiceLogger
from app.db.implementations.in_memory import InMemoryVectorStore
from app.db.interfaces import IVectorStore
from app.messaging.interfaces import IProducer
from app.services.vector_service import VectorService
from shared.context import bound_context


def build_chunk(**overrides):
    """Create a valid chunk payload for tests."""
    chunk = {
        "file_id": "file-1",
        "tenant_id": "tenant-a",
        "owner_user_id": "user-a",
        "owner_admin_id": "admin-a",
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "chunk_index": 0,
        "chunk_version": 3,
        "text": "Clean chunk text for retrieval",
        "text_preview": "Clean chunk text",
        "source_name": "example.pdf",
        "page": 1,
        "section": "intro",
        "retrieval_allowed": True,
        "review_status": "clean",
        "issue_flags": [],
        "created_at": "2026-03-17T10:00:00Z",
        "embedding": [0.1, 0.2, 0.3],
    }
    chunk.update(overrides)
    return chunk


def build_envelope(
    *,
    action,
    message_type,
    payload,
    source_service="rag",
    target_service="vector_db",
    reply_to="rag.replies",
    request_id="req-1",
    trace_id="trace-1",
    correlation_id="corr-1",
    message_id="msg-1",
    timestamp="2026-03-17T10:00:00Z",
    **overrides,
):
    """Create a canonical Kafka envelope for tests."""
    envelope = {
        "message_id": message_id,
        "message_type": message_type,
        "action": action,
        "source_service": source_service,
        "target_service": target_service,
        "request_id": request_id,
        "trace_id": trace_id,
        "correlation_id": correlation_id,
        "timestamp": timestamp,
        "payload": payload,
    }
    if reply_to is not None:
        envelope["reply_to"] = reply_to
    envelope.update(overrides)
    return envelope


@pytest.fixture
def mock_qdrant_client(monkeypatch):
    """Patch the Qdrant client used by the store implementation."""
    client = Mock()
    client.get_collections.return_value = SimpleNamespace(
        collections=[SimpleNamespace(name="rag_chunks_v1")]
    )
    client.count.return_value = SimpleNamespace(count=0)
    client.get_collection.return_value = SimpleNamespace(points_count=0)
    def build_client(**kwargs):
        client.constructor_kwargs = kwargs
        return client

    monkeypatch.setattr("app.db.implementations.qdrant.QdrantClient", build_client)
    return client


@pytest.fixture
def mock_vector_store():
    """Mock vector store."""
    store = Mock(spec=IVectorStore)
    store.collection_name = "rag_chunks_v1"
    store.initialize_collection.return_value = "rag_chunks_v1"
    store.upsert_chunks.return_value = 1
    store.search_chunks.return_value = [
        {
            "id": "chunk-1",
            "score": 0.9,
            "payload": {"chunk_id": "chunk-1", "text": "Clean chunk text"},
        }
    ]
    store.delete_chunks.return_value = 1
    store.count.return_value = 1
    return store


@pytest.fixture
def mock_producer():
    """Mock Kafka producer."""
    producer = Mock(spec=IProducer)
    producer.send = Mock()
    producer.flush = Mock()
    producer.is_connected.return_value = True
    return producer


@pytest.fixture
def mock_logger():
    """Mock structured logger."""
    return Mock(spec=ServiceLogger)


@pytest.fixture
def vector_service(mock_vector_store, mock_producer, mock_logger):
    """Chunk-native vector service instance."""
    return VectorService(
        vector_store=mock_vector_store,
        producer=mock_producer,
        service_logger=mock_logger,
        upsert_completed_topic="vector_db.upsert.completed",
        files_topic="files.requests",
        request_topic="vector_db.requests",
        upsert_requested_topic="vector_db.upsert.requested",
        delete_requested_topic="vector_db.delete.requested",
        service_name="vector_db",
    )


ADMIN_A = {"tenant_id": "tenant-a", "user_id": "admin-a", "role": "admin", "admin_id": "admin-a"}


ADMIN_B = {"tenant_id": "tenant-b", "user_id": "admin-b", "role": "admin", "admin_id": "admin-b"}


@pytest.fixture
def live_service(mock_producer, mock_logger):
    """A vector service over a real in-memory store, for existence checks."""
    return VectorService(
        vector_store=InMemoryVectorStore(),
        producer=mock_producer,
        service_logger=mock_logger,
        upsert_completed_topic="vector_db.upsert.completed",
        files_topic="files.requests",
        request_topic="vector_db.requests",
        upsert_requested_topic="vector_db.upsert.requested",
        delete_requested_topic="vector_db.delete.requested",
        service_name="vector_db",
    )


def seed(service, identity, *chunks):
    """Upsert chunks as one identity, so ownership is the trusted kind."""
    with bound_context(**identity):
        service.upsert_chunks(list(chunks))
