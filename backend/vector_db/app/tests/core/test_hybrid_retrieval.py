"""Focused contracts for sparse representation and deterministic fusion."""
import numpy as np
import pytest

from app.db.implementations.in_memory import InMemoryVectorStore
from app.services.hybrid_retrieval import reciprocal_rank_fusion
from shared.sparse_retrieval import sparse_lexical_vector

from app.tests._vector_harness import build_chunk


def candidate(chunk_id, score):
    return {"id": chunk_id, "score": score, "payload": {"chunk_id": chunk_id}}


def test_sparse_representation_is_deterministic_bounded_and_unicode_aware():
    text = "RPO מסד-נתונים RPO " + " ".join(f"term-{index}" for index in range(600))
    first = sparse_lexical_vector(text)
    second = sparse_lexical_vector(text)

    assert first == second
    assert 0 < len(first["indices"]) <= 512
    assert len(first["indices"]) == len(first["values"])
    assert first["indices"] == sorted(first["indices"])
    assert sparse_lexical_vector("מסד-נתונים") != {"indices": [], "values": []}


def test_sparse_representation_handles_empty_and_invalid_input():
    assert sparse_lexical_vector(" --- ") == {"indices": [], "values": []}
    with pytest.raises(TypeError, match="string"):
        sparse_lexical_vector(None)  # type: ignore[arg-type]


def test_rrf_deduplicates_combines_arms_and_has_stable_ties():
    dense = [candidate("both", 0.9), candidate("dense-only", 0.8)]
    sparse = [candidate("both", 12.0), candidate("sparse-only", 8.0)]

    result = reciprocal_rank_fusion(dense, sparse, limit=3, rrf_k=60)

    assert [item["payload"]["chunk_id"] for item in result] == [
        "both",
        "dense-only",
        "sparse-only",
    ]
    assert result[0]["retrieval_diagnostics"]["matched_arms"] == ["dense", "sparse"]
    assert result[1]["retrieval_diagnostics"]["dense_rank"] == 2
    assert result[2]["retrieval_diagnostics"]["sparse_rank"] == 2
    assert reciprocal_rank_fusion(dense, sparse, limit=3) == result


def test_sparse_arm_can_surface_exact_term_dense_misses_with_filter_parity():
    store = InMemoryVectorStore()
    store.upsert_chunks(
        [
            build_chunk(chunk_id="dense", text="general recovery guidance", embedding=[1, 0, 0]),
            build_chunk(chunk_id="exact", text="application metadata RPO-47X", embedding=[0, 1, 0]),
            build_chunk(
                chunk_id="forbidden",
                text="application metadata RPO-47X",
                embedding=[0, 1, 0],
                retrieval_allowed=False,
            ),
            build_chunk(
                chunk_id="other-tenant",
                tenant_id="tenant-b",
                text="application metadata RPO-47X",
                embedding=[0, 1, 0],
            ),
        ]
    )

    filters = {"tenant_id": "tenant-a"}
    dense = store.search_chunks(np.array([1, 0, 0]), top_k=1, filters=filters)
    sparse = store.search_sparse(
        sparse_lexical_vector("RPO-47X"), top_k=10, filters=filters
    )

    assert [item["payload"]["chunk_id"] for item in dense] == ["dense"]
    assert [item["payload"]["chunk_id"] for item in sparse] == ["exact"]


def test_vector_service_invokes_both_bounded_arms_and_reports_provenance(
    vector_service, mock_vector_store
):
    mock_vector_store.search_chunks.return_value = [candidate("dense", 0.9)]
    mock_vector_store.search_sparse.return_value = [candidate("exact", 5.0)]

    results = vector_service.search_chunks(
        [0.1, 0.2, 0.3],
        top_k=2,
        filters={"tenant_id": "tenant-a"},
        query_sparse={"indices": [7], "values": [1.0]},
        retrieval_strategy="hybrid",
        dense_candidate_k=4,
        sparse_candidate_k=5,
        rrf_k=60,
    )

    assert mock_vector_store.search_chunks.call_args.kwargs["top_k"] == 4
    assert mock_vector_store.search_sparse.call_args.kwargs["top_k"] == 5
    assert (
        mock_vector_store.search_chunks.call_args.kwargs["filters"]
        == mock_vector_store.search_sparse.call_args.kwargs["filters"]
    )
    assert [item["retrieval_diagnostics"]["matched_arms"] for item in results] == [
        ["dense"],
        ["sparse"],
    ]
