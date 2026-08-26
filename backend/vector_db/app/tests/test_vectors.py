"""Tests for chunk-native vector_db behavior and Kafka contracts."""
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, call

import numpy as np
import pytest

from app.core.constants import MAX_VERIFY_IDS
from app.core.errors import InvalidVectorError
from app.core.logging_config import ServiceLogger
from app.db.implementations.in_memory import InMemoryVectorStore
from app.db.implementations.qdrant import INDEXED_FIELDS, QdrantVectorStore
from app.db.interfaces import IVectorStore
from app.messaging.interfaces import IProducer
from app.services.vector_service import VectorService
from shared.auth import AuthError
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


def test_user_search_overrides_client_tenant_and_owner_filters(vector_service, mock_vector_store):
    with bound_context(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    ):
        vector_service.search_chunks(
            [0.1, 0.2, 0.3],
            filters={"tenant_id": "tenant-b", "owner_user_id": "user-b", "file_id": "file-a"},
        )

    filters = mock_vector_store.search_chunks.call_args.kwargs["filters"]
    assert filters == {
        "tenant_id": "tenant-a",
        "owner_user_id": "user-a",
        "file_id": "file-a",
    }


def test_admin_search_is_limited_to_managed_users(vector_service, mock_vector_store):
    with bound_context(
        tenant_id="tenant-a",
        user_id="admin-a",
        role="admin",
        admin_id="admin-a",
    ):
        vector_service.search_chunks([0.1, 0.2, 0.3], filters={"owner_user_id": "user-a"})

    assert mock_vector_store.search_chunks.call_args.kwargs["filters"] == {
        "tenant_id": "tenant-a",
        "owner_admin_id": "admin-a",
    }


def test_user_chunk_write_uses_trusted_ownership(vector_service, mock_vector_store):
    with bound_context(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    ):
        vector_service.upsert_chunks([build_chunk(tenant_id="tenant-a", owner_user_id="forged")])

    chunk = mock_vector_store.upsert_chunks.call_args.args[0][0]
    assert chunk["tenant_id"] == "tenant-a"
    assert chunk["owner_user_id"] == "user-a"
    assert chunk["owner_admin_id"] == "admin-a"


def test_vector_scope_fails_closed_without_identity_in_production(vector_service, monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    with pytest.raises(AuthError, match="identity is missing"):
        vector_service.search_chunks([0.1, 0.2, 0.3])


def test_initialize_collection_creates_collection_and_payload_indexes(mock_qdrant_client):
    """Collection bootstrap should create the collection and all required payload indexes."""
    mock_qdrant_client.get_collections.return_value = SimpleNamespace(collections=[])

    store = QdrantVectorStore(vector_size=3)

    assert store.collection_name == "rag_chunks_v1"
    mock_qdrant_client.create_collection.assert_called_once()
    indexed_fields = {
        call.kwargs["field_name"]
        for call in mock_qdrant_client.create_payload_index.call_args_list
    }
    assert indexed_fields == set(INDEXED_FIELDS.keys())


def test_qdrant_internal_connection_explicitly_disables_tls(mock_qdrant_client):
    QdrantVectorStore(vector_size=3, api_key="test-api-key", https=False)

    assert mock_qdrant_client.constructor_kwargs["https"] is False
    assert mock_qdrant_client.constructor_kwargs["api_key"] == "test-api-key"


def test_initialize_collection_reuses_existing_collection(mock_qdrant_client):
    """Existing equivalent collections should be reused instead of recreated."""
    QdrantVectorStore(vector_size=3)

    mock_qdrant_client.create_collection.assert_not_called()
    assert mock_qdrant_client.create_payload_index.call_count == len(INDEXED_FIELDS)


def test_upsert_chunks_uses_deterministic_chunk_id_points(mock_qdrant_client):
    """Repeated upsert should keep the same deterministic point ID."""
    store = QdrantVectorStore(vector_size=3)
    chunk = build_chunk()

    first_count = store.upsert_chunks([chunk])
    first_points = mock_qdrant_client.upsert.call_args.kwargs["points"]

    second_count = store.upsert_chunks([chunk])
    second_points = mock_qdrant_client.upsert.call_args.kwargs["points"]

    assert first_count == 1
    assert second_count == 1
    expected_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "tenant-a:chunk-1"))
    assert first_points[0].id == expected_id
    assert second_points[0].id == expected_id


def test_upsert_chunks_rejects_dimension_mismatch(mock_qdrant_client):
    """Chunk upsert should reject embeddings that do not match the configured dimension."""
    store = QdrantVectorStore(vector_size=3)

    with pytest.raises(ValueError, match="Vector size mismatch"):
        store.upsert_chunks([build_chunk(embedding=[0.1, 0.2])])


def test_count_uses_qdrant_count_endpoint_before_collection_info(mock_qdrant_client):
    """Point count should use the dedicated count endpoint first for server compatibility."""
    mock_qdrant_client.count.return_value = SimpleNamespace(count=7)
    mock_qdrant_client.get_collection.side_effect = RuntimeError("should not be used")

    store = QdrantVectorStore(vector_size=3)

    assert store.count() == 7
    mock_qdrant_client.count.assert_called_with(
        collection_name="rag_chunks_v1",
        exact=True,
    )


def test_count_falls_back_to_collection_info_when_count_endpoint_fails(mock_qdrant_client):
    """Older-compatible collection info can still be used if the count endpoint fails."""
    mock_qdrant_client.count.side_effect = RuntimeError("count unavailable")
    mock_qdrant_client.get_collection.return_value = SimpleNamespace(points_count=11)

    store = QdrantVectorStore(vector_size=3)

    assert store.count() == 11


def test_search_chunks_enforces_internal_safety_filter(mock_qdrant_client):
    """Search must always enforce retrieval_allowed=true and review_status!=removed."""
    store = QdrantVectorStore(vector_size=3)
    mock_qdrant_client.search.return_value = [
        SimpleNamespace(id="chunk-1", score=0.91, payload={"chunk_id": "chunk-1"})
    ]

    results = store.search_chunks(
        query_vector=np.array([0.1, 0.2, 0.3], dtype=np.float32),
        filters={
            "file_id": "file-1",
            "retrieval_allowed": False,
            "review_status": "removed",
        },
        include_payload=True,
        include_vector=False,
    )

    query_filter = mock_qdrant_client.search.call_args.kwargs["query_filter"]
    filter_dump = query_filter.model_dump(exclude_none=True)
    must_conditions = filter_dump["must"]
    must_not_conditions = filter_dump["must_not"]

    assert {"key": "retrieval_allowed", "match": {"value": True}} in must_conditions
    assert {"key": "file_id", "match": {"value": "file-1"}} in must_conditions
    assert {"key": "review_status", "match": {"value": "removed"}} in must_not_conditions
    assert all(
        not (
            condition["key"] == "review_status"
            and condition["match"].get("value") == "removed"
        )
        for condition in must_conditions
    )
    assert results[0]["payload"]["chunk_id"] == "chunk-1"


@pytest.mark.parametrize(
    "filters",
    [
        {"file_id": "file-1"},
        {"document_id": "doc-1"},
        {"file_id": "file-1", "document_id": "doc-1"},
    ],
)
def test_delete_chunks_supports_file_document_and_combined_filters(
    mock_qdrant_client,
    filters,
):
    """Delete should support file_id, document_id, or both together."""
    store = QdrantVectorStore(vector_size=3)
    mock_qdrant_client.scroll.return_value = (
        [SimpleNamespace(id="chunk-1"), SimpleNamespace(id="chunk-2")],
        None,
    )

    deleted_count = store.delete_chunks(filters)

    assert deleted_count == 2
    delete_filter = mock_qdrant_client.scroll.call_args.kwargs["scroll_filter"]
    filter_dump = delete_filter.model_dump(exclude_none=True)
    assert {condition["key"] for condition in filter_dump["must"]} == set(filters.keys())
    assert mock_qdrant_client.delete.call_args.kwargs["points_selector"] == [
        "chunk-1",
        "chunk-2",
    ]


def test_remove_problematic_text_deletes_then_upserts_sanitized_chunks(
    vector_service,
    mock_vector_store,
):
    """Sanitized replacement should use ordered delete-then-upsert semantics."""
    chunk = build_chunk(review_status="clean")

    result = vector_service.upsert_chunks(
        chunks=[chunk],
        review_outcome="remove_problematic_text",
        target_filters={"document_id": "doc-1"},
    )

    expected_chunk = build_chunk(review_status="sanitized")
    assert mock_vector_store.method_calls[:2] == [
        call.delete_chunks({"document_id": "doc-1"}),
        call.upsert_chunks([expected_chunk]),
    ]
    assert result["deleted_count"] == 1
    assert result["upserted_count"] == 1


def test_accept_as_is_keeps_chunks_searchable_with_accepted_with_risk_status(
    vector_service,
    mock_vector_store,
):
    """accept_as_is should preserve searchability while forcing accepted_with_risk."""
    vector_service.upsert_chunks(
        chunks=[build_chunk(review_status="clean", retrieval_allowed=True)],
        review_outcome="accept_as_is",
    )

    upserted_chunk = mock_vector_store.upsert_chunks.call_args.args[0][0]
    assert upserted_chunk["review_status"] == "accepted_with_risk"
    assert upserted_chunk["retrieval_allowed"] is True


def test_canonical_search_query_replies_with_shared_envelope(
    vector_service,
    mock_producer,
):
    """Canonical search requests should receive a canonical reply envelope."""
    request = build_envelope(
        action="search_chunks",
        message_type="query",
        source_service="rag",
        reply_to="rag.replies",
        payload={
            "query_vector": [0.1, 0.2, 0.3],
            "top_k": 5,
            "filters": {"file_id": "file-1", "review_status": "removed"},
            "include_payload": True,
            "include_vector": False,
        },
    )

    vector_service.process_kafka_message("vector_db.requests", request)

    assert mock_producer.send.call_count == 1
    reply_topic, reply_message = mock_producer.send.call_args.args
    assert reply_topic == "rag.replies"
    assert reply_message["message_type"] == "reply"
    assert reply_message["action"] == "search_chunks"
    assert reply_message["source_service"] == "vector_db"
    assert reply_message["target_service"] == "rag"
    assert reply_message["request_id"] == "req-1"
    assert reply_message["trace_id"] == "trace-1"
    assert reply_message["correlation_id"] == "corr-1"
    assert reply_message["success"] is True
    assert reply_message["payload"]["results"][0]["score"] == 0.9
    assert reply_message["payload"]["results"][0]["payload"]["chunk_id"] == "chunk-1"


def test_legacy_flat_search_request_is_normalized_for_compatibility(
    vector_service,
    mock_producer,
):
    """Legacy flat search requests should still work during the migration."""
    request = {
        "action": "search_chunks",
        "request_id": "req-legacy",
        "trace_id": "trace-legacy",
        "correlation_id": "corr-legacy",
        "reply_to": "rag.replies",
        "query_vector": [0.1, 0.2, 0.3],
        "top_k": 5,
        "filters": {"file_id": "file-1", "review_status": "removed"},
        "include_payload": True,
        "include_vector": False,
    }

    vector_service.process_kafka_message("vector_db.requests", request)

    assert mock_producer.send.call_count == 1
    reply_topic, reply_message = mock_producer.send.call_args.args
    assert reply_topic == "rag.replies"
    assert reply_message["message_type"] == "reply"
    assert reply_message["source_service"] == "vector_db"
    assert reply_message["target_service"] == "rag"
    assert reply_message["request_id"] == "req-legacy"
    assert reply_message["trace_id"] == "trace-legacy"
    assert reply_message["correlation_id"] == "corr-legacy"
    assert reply_message["success"] is True
    assert "message_id" in reply_message
    assert "timestamp" in reply_message


def test_search_request_coerces_numeric_timestamp_to_string(
    vector_service,
    mock_producer,
):
    """Typed search requests should accept numeric timestamps from mixed callers."""
    request = build_envelope(
        action="search_chunks",
        message_type="query",
        payload={
            "query_vector": [0.1, 0.2, 0.3],
            "top_k": 3,
            "filters": {},
            "include_payload": True,
            "include_vector": False,
        },
        timestamp=1773849674729,
    )

    vector_service.process_kafka_message("vector_db.requests", request)

    reply_topic, reply_message = mock_producer.send.call_args.args
    assert reply_topic == "rag.replies"
    assert isinstance(reply_message["timestamp"], str)


def test_canonical_upsert_command_publishes_reply_and_completion_event(
    vector_service,
    mock_producer,
):
    """Canonical upsert commands should emit a reply and the completion event."""
    request = build_envelope(
        action="upsert_chunks",
        message_type="command",
        source_service="gateway",
        reply_to="gateway.replies",
        request_id="req-2",
        trace_id="trace-2",
        correlation_id="corr-2",
        message_id="msg-2",
        payload={
            "review_outcome": "accept_as_is",
            "chunks": [build_chunk()],
        },
    )

    vector_service.process_kafka_message("vector_db.upsert.requested", request)

    assert mock_producer.send.call_count == 4
    reply_topic, reply_message = mock_producer.send.call_args_list[0].args
    event_topic, event_message = mock_producer.send.call_args_list[1].args
    files_topic_one, files_message_one = mock_producer.send.call_args_list[2].args
    files_topic_two, files_message_two = mock_producer.send.call_args_list[3].args

    assert reply_topic == "gateway.replies"
    assert reply_message["message_type"] == "reply"
    assert reply_message["action"] == "upsert_chunks"
    assert reply_message["source_service"] == "vector_db"
    assert reply_message["target_service"] == "gateway"
    assert reply_message["request_id"] == "req-2"
    assert reply_message["trace_id"] == "trace-2"
    assert reply_message["correlation_id"] == "corr-2"
    assert reply_message["success"] is True
    assert reply_message["payload"]["collection_name"] == "rag_chunks_v1"

    assert event_topic == "vector_db.upsert.completed"
    assert event_message["message_type"] == "event"
    assert event_message["action"] == "upsert_chunks"
    assert event_message["event_type"] == "vector_db.upsert.completed"
    assert event_message["source_service"] == "vector_db"
    assert event_message["target_service"] == "gateway"
    assert event_message["request_id"] == "req-2"
    assert event_message["trace_id"] == "trace-2"
    assert event_message["correlation_id"] == "corr-2"
    assert event_message["payload"]["status"] == "success"
    assert event_message["payload"]["review_outcome"] == "accept_as_is"
    assert event_message["payload"]["collection_name"] == "rag_chunks_v1"
    assert files_topic_one == "files.requests"
    assert files_message_one["action"] == "update_stage"
    assert files_message_one["payload"] == {
        "file_id": "file-1",
        "stage": "semantic",
        "status": "done",
    }
    assert files_topic_two == "files.requests"
    assert files_message_two["action"] == "update_stage"
    assert files_message_two["payload"] == {
        "file_id": "file-1",
        "stage": "vector",
        "status": "done",
    }


def test_canonical_delete_command_replies_with_shared_envelope(
    vector_service,
    mock_producer,
    mock_vector_store,
):
    """Canonical delete commands should work on the dedicated delete topic."""
    request = build_envelope(
        action="delete_chunks",
        message_type="command",
        source_service="gateway",
        reply_to="gateway.replies",
        request_id="req-3",
        trace_id="trace-3",
        correlation_id="corr-3",
        message_id="msg-3",
        payload={
            "review_outcome": "delete_file",
            "filters": {"file_id": "file-1", "document_id": "doc-1"},
        },
    )

    vector_service.process_kafka_message("vector_db.delete.requested", request)

    mock_vector_store.delete_chunks.assert_called_once_with(
        {"file_id": "file-1", "document_id": "doc-1"}
    )
    assert mock_producer.send.call_count == 1
    reply_topic, reply_message = mock_producer.send.call_args.args
    assert reply_topic == "gateway.replies"
    assert reply_message["message_type"] == "reply"
    assert reply_message["action"] == "delete_chunks"
    assert reply_message["source_service"] == "vector_db"
    assert reply_message["target_service"] == "gateway"
    assert reply_message["success"] is True
    assert reply_message["payload"]["review_outcome"] == "delete_file"


def test_files_cleanup_event_is_normalized_on_delete_requested_topic(
    vector_service,
    mock_producer,
    mock_vector_store,
):
    """The files cleanup event should be normalized into the canonical delete flow."""
    request = build_envelope(
        action="vector_db.delete.requested",
        message_type="event",
        source_service="files",
        target_service="vector_db",
        reply_to="gateway.replies",
        request_id="req-files-delete",
        trace_id="trace-files-delete",
        correlation_id="corr-files-delete",
        message_id="msg-files-delete",
        payload={
            "event_id": "evt-1",
            "event_type": "vector_db.delete.requested",
            "file_id": "file-1",
            "document_id": "doc-1",
            "task_id": "task-1",
            "reason": "explicit_delete",
            "delete_chunks": True,
            "delete_vectors": True,
            "created_at": "2026-03-18T10:00:00Z",
        },
    )

    vector_service.process_kafka_message("vector_db.delete.requested", request)

    mock_vector_store.delete_chunks.assert_called_once_with(
        {"file_id": "file-1", "document_id": "doc-1"}
    )
    assert mock_producer.send.call_count == 1
    reply_topic, reply_message = mock_producer.send.call_args.args
    assert reply_topic == "gateway.replies"
    assert reply_message["message_type"] == "reply"
    assert reply_message["action"] == "delete_chunks"
    assert reply_message["source_service"] == "vector_db"
    assert reply_message["target_service"] == "files"
    assert reply_message["request_id"] == "req-files-delete"
    assert reply_message["trace_id"] == "trace-files-delete"
    assert reply_message["correlation_id"] == "corr-files-delete"
    assert reply_message["success"] is True
    assert reply_message["payload"]["review_outcome"] == "delete_file"
    assert reply_message["payload"]["filters"] == {
        "file_id": "file-1",
        "document_id": "doc-1",
    }


def test_files_cleanup_event_without_scope_replies_with_validation_error(
    vector_service,
    mock_producer,
):
    """Compatibility delete events still require file_id or document_id."""
    request = build_envelope(
        action="vector_db.delete.requested",
        message_type="event",
        source_service="files",
        target_service="vector_db",
        reply_to="gateway.replies",
        request_id="req-files-delete-invalid",
        trace_id="trace-files-delete-invalid",
        correlation_id="corr-files-delete-invalid",
        message_id="msg-files-delete-invalid",
        payload={
            "event_id": "evt-2",
            "event_type": "vector_db.delete.requested",
            "task_id": "task-2",
            "reason": "explicit_delete",
            "delete_chunks": True,
            "delete_vectors": True,
            "created_at": "2026-03-18T10:05:00Z",
        },
    )

    vector_service.process_kafka_message("vector_db.delete.requested", request)

    assert mock_producer.send.call_count == 1
    reply_topic, reply_message = mock_producer.send.call_args.args
    assert reply_topic == "gateway.replies"
    assert reply_message["message_type"] == "reply"
    assert reply_message["action"] == "delete_chunks"
    assert reply_message["source_service"] == "vector_db"
    assert reply_message["target_service"] == "files"
    assert reply_message["request_id"] == "req-files-delete-invalid"
    assert reply_message["trace_id"] == "trace-files-delete-invalid"
    assert reply_message["correlation_id"] == "corr-files-delete-invalid"
    assert reply_message["success"] is False
    assert "filters must include file_id, document_id, or both" in reply_message["error"]["message"]


def test_legacy_flat_upsert_request_is_normalized_for_compatibility(
    vector_service,
    mock_producer,
):
    """Legacy flat upsert requests should still produce canonical replies and events."""
    request = {
        "action": "upsert_chunks",
        "request_id": "req-legacy-upsert",
        "trace_id": "trace-legacy-upsert",
        "correlation_id": "corr-legacy-upsert",
        "reply_to": "gateway.replies",
        "review_outcome": "none",
        "chunks": [build_chunk()],
    }

    vector_service.process_kafka_message("vector_db.upsert.requested", request)

    assert mock_producer.send.call_count == 4
    reply_topic, reply_message = mock_producer.send.call_args_list[0].args
    event_topic, event_message = mock_producer.send.call_args_list[1].args
    assert reply_topic == "gateway.replies"
    assert reply_message["message_type"] == "reply"
    assert reply_message["source_service"] == "vector_db"
    assert reply_message["target_service"] == "gateway"
    assert event_topic == "vector_db.upsert.completed"
    assert event_message["message_type"] == "event"
    assert event_message["source_service"] == "vector_db"
    assert event_message["target_service"] == "gateway"


def test_service_raises_invalid_vector_error_for_empty_query(vector_service):
    """The service should reject empty query vectors before hitting the store."""
    with pytest.raises(InvalidVectorError, match="query_vector is required"):
        vector_service.search_chunks([])


# -- Golden-set label verification ----------------------------------------
#
# `verify_chunk_ids` exists so the eval harness can tell a retrieval miss
# from a benchmark label whose chunk no longer exists. It must never become
# a way to look outside the caller's own tenant, so most of what follows is
# about what it refuses rather than what it returns.


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


def test_an_existing_chunk_id_verifies_as_present_and_retrievable(live_service):
    seed(live_service, ADMIN_A, build_chunk(chunk_id="chunk-live"))

    with bound_context(**ADMIN_A):
        result = live_service.verify_chunk_ids(chunk_ids=["chunk-live"])

    assert result["chunk_ids"]["present"] == ["chunk-live"]
    assert result["chunk_ids"]["retrievable"] == ["chunk-live"]
    assert result["chunk_ids"]["missing"] == []


def test_a_deleted_chunk_id_verifies_as_missing(live_service):
    """The whole point: reindexing dropped the chunk the label names."""
    seed(live_service, ADMIN_A, build_chunk(chunk_id="chunk-gone"))
    with bound_context(**ADMIN_A):
        live_service.delete_chunks({"file_id": "file-1"})
        result = live_service.verify_chunk_ids(chunk_ids=["chunk-gone"])

    assert result["chunk_ids"]["missing"] == ["chunk-gone"]
    assert result["chunk_ids"]["present"] == []


def test_file_ids_are_verified_as_well_as_chunk_ids(live_service):
    """A file-level golden set labels files, and drifts the same way."""
    seed(live_service, ADMIN_A, build_chunk(chunk_id="chunk-1", file_id="file-kept"))

    with bound_context(**ADMIN_A):
        result = live_service.verify_chunk_ids(file_ids=["file-kept", "file-dropped"])

    assert result["file_ids"]["present"] == ["file-kept"]
    assert result["file_ids"]["missing"] == ["file-dropped"]
    # The chunk field was not asked about and reports nothing, rather than
    # borrowing the file answer.
    assert result["chunk_ids"] == {"present": [], "retrievable": [], "missing": []}


def test_another_tenants_chunk_id_is_indistinguishable_from_a_deleted_one(live_service):
    """Cross-tenant ids must not be verifiable - existence is information."""
    seed(
        live_service,
        ADMIN_B,
        build_chunk(
            chunk_id="chunk-b",
            tenant_id="tenant-b",
            owner_user_id="user-b",
            owner_admin_id="admin-b",
        ),
    )

    with bound_context(**ADMIN_A):
        result = live_service.verify_chunk_ids(chunk_ids=["chunk-b"])

    assert result["chunk_ids"]["missing"] == ["chunk-b"]
    assert result["chunk_ids"]["present"] == []


def test_verification_scope_comes_from_the_identity_not_the_payload(
    vector_service,
    mock_vector_store,
):
    """There is no filter argument to forge, and the scope is the caller's."""
    mock_vector_store.lookup_ids.return_value = {"present": [], "retrievable": []}

    with bound_context(**ADMIN_A):
        vector_service.verify_chunk_ids(chunk_ids=["c1"])

    field, values, filters = mock_vector_store.lookup_ids.call_args.args
    assert field == "chunk_id"
    assert values == ["c1"]
    assert filters == {"tenant_id": "tenant-a", "owner_admin_id": "admin-a"}


def test_verification_fails_closed_without_an_identity_in_production(
    vector_service,
    monkeypatch,
):
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    with pytest.raises(AuthError, match="identity is missing"):
        vector_service.verify_chunk_ids(chunk_ids=["c1"])


def test_verification_without_any_id_is_refused(vector_service):
    """An empty request is the one shape that would mean 'show me anything'."""
    with bound_context(**ADMIN_A):
        with pytest.raises(InvalidVectorError, match="chunk_ids, file_ids, or both"):
            vector_service.verify_chunk_ids()


def test_a_chunk_barred_from_retrieval_is_present_but_not_retrievable(live_service):
    """Neither a deleted label nor a reachable one - a third state."""
    seed(
        live_service,
        ADMIN_A,
        build_chunk(chunk_id="chunk-blocked", review_status="removed"),
    )

    with bound_context(**ADMIN_A):
        result = live_service.verify_chunk_ids(chunk_ids=["chunk-blocked"])

    assert result["chunk_ids"]["present"] == ["chunk-blocked"]
    assert result["chunk_ids"]["retrievable"] == []
    assert result["chunk_ids"]["missing"] == []


def test_lookup_ids_refuses_a_field_that_is_not_an_id(live_service):
    """`text` would turn an existence check into a content query."""
    with pytest.raises(ValueError, match="not a verifiable id field"):
        live_service.vector_store.lookup_ids("text", ["anything"])


def test_lookup_ids_refuses_more_ids_than_the_cap(live_service):
    with pytest.raises(ValueError, match="the limit is"):
        live_service.vector_store.lookup_ids(
            "chunk_id", [f"c{index}" for index in range(MAX_VERIFY_IDS + 1)]
        )


def test_qdrant_lookup_bounds_the_scroll_to_the_ids_that_were_asked_about(
    mock_qdrant_client,
):
    """Without the id condition this would be an arbitrary collection scroll."""
    store = QdrantVectorStore(vector_size=3)
    mock_qdrant_client.scroll.return_value = (
        [
            SimpleNamespace(
                id="p1",
                payload={
                    "chunk_id": "c1",
                    "retrieval_allowed": True,
                    "review_status": "clean",
                },
            )
        ],
        None,
    )

    result = store.lookup_ids(
        "chunk_id", ["c1", "c2"], {"tenant_id": "tenant-a", "owner_admin_id": "admin-a"}
    )

    scroll_filter = mock_qdrant_client.scroll.call_args.kwargs["scroll_filter"]
    conditions = {
        condition.key: condition.match.model_dump() for condition in scroll_filter.must
    }
    assert conditions["chunk_id"] == {"any": ["c1", "c2"]}
    assert conditions["tenant_id"] == {"value": "tenant-a"}
    assert conditions["owner_admin_id"] == {"value": "admin-a"}
    # No chunk text is read back: an existence check needs the id and the two
    # safety flags, and nothing else.
    assert mock_qdrant_client.scroll.call_args.kwargs["with_payload"] == [
        "chunk_id",
        "retrieval_allowed",
        "review_status",
    ]
    assert result == {"present": ["c1"], "retrievable": ["c1"]}


def test_verify_chunk_ids_replies_over_rpc_with_the_shared_envelope(
    vector_service,
    mock_vector_store,
):
    mock_vector_store.lookup_ids.return_value = {"present": ["c1"], "retrievable": ["c1"]}
    request = build_envelope(
        action="verify_chunk_ids",
        message_type="query",
        payload={"chunk_ids": ["c1", "c2"]},
    )

    with bound_context(**ADMIN_A):
        reply = vector_service.process_request(request)

    assert reply["success"] is True
    assert reply["action"] == "verify_chunk_ids"
    assert reply["payload"]["chunk_ids"]["present"] == ["c1"]
    assert reply["payload"]["chunk_ids"]["missing"] == ["c2"]


def test_verify_chunk_ids_rpc_refuses_an_empty_request(vector_service):
    request = build_envelope(
        action="verify_chunk_ids",
        message_type="query",
        payload={"chunk_ids": [], "file_ids": []},
    )

    with bound_context(**ADMIN_A):
        reply = vector_service.process_request(request)

    assert reply["success"] is False
    assert "chunk_ids, file_ids, or both are required" in reply["error"]["message"]


def test_search_still_asks_the_store_for_a_ranked_search(vector_service, mock_vector_store):
    """Verification is additive: retrieval's own call is unchanged."""
    with bound_context(**ADMIN_A):
        vector_service.search_chunks([0.1, 0.2, 0.3], top_k=7)

    assert mock_vector_store.search_chunks.call_args.kwargs["top_k"] == 7
    mock_vector_store.lookup_ids.assert_not_called()
