"""The production Qdrant adapter contract: collections, points and filters."""

from types import SimpleNamespace
import numpy as np
import pytest
import uuid

from app.db.implementations.qdrant import INDEXED_FIELDS
from app.db.implementations.qdrant import QdrantVectorStore

from app.tests._vector_harness import (
    build_chunk,
)


"""The production Qdrant adapter contract: collections, points and filters."""


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
    mock_qdrant_client.query_points.return_value = SimpleNamespace(
        points=[SimpleNamespace(id="chunk-1", score=0.91, payload={"chunk_id": "chunk-1"})]
    )

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

    query_filter = mock_qdrant_client.query_points.call_args.kwargs["query_filter"]
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
