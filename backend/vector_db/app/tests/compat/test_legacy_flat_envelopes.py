"""Flat, pre-envelope request shapes still accepted from older producers."""

from app.tests._vector_harness import (
    build_chunk,
)


"""Flat, pre-envelope request shapes still accepted from older producers."""


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
