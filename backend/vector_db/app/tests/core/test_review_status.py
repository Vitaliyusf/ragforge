"""Review decisions reaching the vector store: sanitize, or keep with risk."""

from unittest.mock import call

from app.tests._vector_harness import (
    build_chunk,
)


"""Review decisions reaching the vector store: sanitize, or keep with risk."""


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
