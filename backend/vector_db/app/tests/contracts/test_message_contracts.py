"""Canonical Kafka/RPC envelopes in and out of the vector service."""

import pytest

from app.core.errors import InvalidVectorError
from shared.context import bound_context

from app.tests._vector_harness import (
    ADMIN_A,
    build_chunk,
    build_envelope,
)


"""Canonical Kafka/RPC envelopes in and out of the vector service."""


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


def test_service_raises_invalid_vector_error_for_empty_query(vector_service):
    """The service should reject empty query vectors before hitting the store."""
    with pytest.raises(InvalidVectorError, match="query_vector is required"):
        vector_service.search_chunks([])


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
