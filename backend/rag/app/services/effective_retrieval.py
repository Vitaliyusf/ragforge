"""Truthful provenance for the retrieval stages the live code executes."""
from __future__ import annotations

from typing import Any, Dict, Optional


RETRIEVAL_STRATEGY_DENSE_VECTOR = "dense_vector"
RERANKER_IMPLEMENTATION_CROSS_ENCODER = "sentence_transformers_cross_encoder"

EFFECTIVE_RETRIEVAL_FIELDS = frozenset(
    {
        "retrieval_strategy",
        "hybrid_search_active",
        "dense_active",
        "sparse_active",
        "fusion",
        "dense_candidate_k",
        "sparse_candidate_k",
        "fused_candidate_k",
        "rrf_k",
        "reranker_active",
        "reranker_implementation",
        "reranker_model",
        "reranker_model_revision",
        "reranker_candidate_k",
        "min_similarity_threshold_applied",
        "context_k",
        "merge_kept_k",
        "pass_two_active",
        "pass_two_chunk_threshold",
        "pass_two_score_threshold",
    }
)


def effective_retrieval_config(
    config: Any,
    *,
    pipeline_active: bool,
    pipeline_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Describe retrieval and only the downstream stages the caller reaches."""
    top_k: Optional[int] = getattr(config, "top_k_documents", None)
    hybrid_active = bool(getattr(config, "hybrid_search_enabled", False))
    extended_active = pipeline_active and pipeline_mode != "regular"
    return {
        "retrieval_strategy": (
            "hybrid" if hybrid_active else RETRIEVAL_STRATEGY_DENSE_VECTOR
        ),
        "hybrid_search_active": hybrid_active,
        "dense_active": True,
        "sparse_active": hybrid_active,
        "fusion": "rrf" if hybrid_active else None,
        "dense_candidate_k": getattr(config, "dense_candidate_k", None),
        "sparse_candidate_k": (
            getattr(config, "sparse_candidate_k", None) if hybrid_active else None
        ),
        "fused_candidate_k": (
            getattr(config, "reranker_candidate_k", top_k)
            if hybrid_active and getattr(config, "reranker_enabled", False)
            else (top_k if hybrid_active else None)
        ),
        "rrf_k": getattr(config, "hybrid_rrf_k", None) if hybrid_active else None,
        "reranker_active": bool(getattr(config, "reranker_enabled", False)),
        "reranker_implementation": (
            RERANKER_IMPLEMENTATION_CROSS_ENCODER
            if getattr(config, "reranker_enabled", False)
            else None
        ),
        "reranker_model": (
            getattr(config, "reranker_model", None)
            if getattr(config, "reranker_enabled", False)
            else None
        ),
        "reranker_model_revision": (
            getattr(config, "reranker_model_revision", None)
            if getattr(config, "reranker_enabled", False)
            else None
        ),
        "reranker_candidate_k": (
            getattr(config, "reranker_candidate_k", None)
            if getattr(config, "reranker_enabled", False)
            else None
        ),
        "min_similarity_threshold_applied": None,
        "context_k": top_k if pipeline_active else None,
        "merge_kept_k": (
            getattr(config, "reranker_candidate_k", None) if extended_active else None
        ),
        "pass_two_active": extended_active,
        "pass_two_chunk_threshold": (
            getattr(config, "pass_two_chunk_threshold", None)
            if extended_active
            else None
        ),
        "pass_two_score_threshold": (
            getattr(config, "pass_two_score_threshold", None)
            if extended_active
            else None
        ),
    }
