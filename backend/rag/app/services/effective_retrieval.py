"""Truthful provenance for the retrieval stages the live code executes."""
from __future__ import annotations

from typing import Any, Dict, Optional


RETRIEVAL_STRATEGY_DENSE_VECTOR = "dense_vector"
MERGE_IMPLEMENTATION_SCORE_ORDER = "score_order_merge"
MERGE_KEPT_MULTIPLIER = 2

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
) -> Dict[str, Any]:
    """Describe retrieval and only the downstream stages the caller reaches."""
    top_k: Optional[int] = getattr(config, "top_k_documents", None)
    hybrid_active = bool(getattr(config, "hybrid_search_enabled", False))
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
        "fused_candidate_k": top_k if hybrid_active else None,
        "rrf_k": getattr(config, "hybrid_rrf_k", None) if hybrid_active else None,
        "reranker_active": False,
        "reranker_implementation": (
            MERGE_IMPLEMENTATION_SCORE_ORDER if pipeline_active else None
        ),
        "reranker_model": None,
        "min_similarity_threshold_applied": None,
        "context_k": top_k if pipeline_active else None,
        "merge_kept_k": (
            top_k * MERGE_KEPT_MULTIPLIER
            if pipeline_active and isinstance(top_k, int)
            else None
        ),
        "pass_two_active": pipeline_active,
        "pass_two_chunk_threshold": (
            getattr(config, "pass_two_chunk_threshold", None)
            if pipeline_active
            else None
        ),
        "pass_two_score_threshold": (
            getattr(config, "pass_two_score_threshold", None)
            if pipeline_active
            else None
        ),
    }
