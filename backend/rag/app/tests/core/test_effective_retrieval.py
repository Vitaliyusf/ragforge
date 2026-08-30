"""Tests for what the retrieval pipeline is reported to actually do.

The defect these guard against is a specific one. ``RAGConfig`` carries a
block of fields its own comment marks "Legacy fields retained for
compatibility" — ``reranker_enabled`` and ``hybrid_search_enabled`` among
them — which default to ``True`` and which no retrieval code reads. Every
provenance record that copied them said a reranker and a hybrid retriever
produced its numbers. Neither exists: ``search_chunks`` sends only a query
vector and a ``top_k``; RAG-04 replaces the former score-only merge with an
actual cross-encoder stage.

So the first thing asserted below is that a true legacy flag does not survive
into an "active" claim. The second is the distinction that makes the nulls
readable: a null here means "provably absent", never "not captured", which is
the exact opposite of what a null means in the env-sourced half of a config
snapshot.
"""
from __future__ import annotations

from app.core.config import RAGConfig
from app.services.effective_retrieval import (
    EFFECTIVE_RETRIEVAL_FIELDS,
    effective_retrieval_config,
)


def config() -> RAGConfig:
    return RAGConfig(reranker_enabled=True)


def test_the_enabled_learned_reranker_is_reported_with_a_pinned_model():
    """The acceptance criterion, stated directly."""
    live = config()
    assert live.reranker_enabled is True

    effective = effective_retrieval_config(live, pipeline_active=True)

    assert effective["reranker_active"] is True
    # Null because there is no second model scoring a candidate — the only
    # ordering in the pipeline is the vector store's own.
    assert effective["reranker_model"] == live.reranker_model
    assert effective["reranker_model_revision"] == live.reranker_model_revision
    assert effective["reranker_candidate_k"] == live.reranker_candidate_k
    assert effective["reranker_implementation"] == "sentence_transformers_cross_encoder"


def test_a_disabled_reranker_reports_proven_absence():
    effective = effective_retrieval_config(
        RAGConfig(reranker_enabled=False), pipeline_active=True
    )

    assert effective["reranker_active"] is False
    assert effective["reranker_model"] is None
    assert effective["reranker_model_revision"] is None
    assert effective["reranker_implementation"] is None


def test_effective_config_reports_the_real_hybrid_path():
    live = config()
    assert live.hybrid_search_enabled is True

    effective = effective_retrieval_config(live, pipeline_active=True)

    assert effective["retrieval_strategy"] == "hybrid"
    assert effective["hybrid_search_active"] is True
    assert effective["dense_active"] is True
    assert effective["sparse_active"] is True
    assert effective["fusion"] == "rrf"
    assert effective["dense_candidate_k"] == live.dense_candidate_k
    assert effective["sparse_candidate_k"] == live.sparse_candidate_k
    assert effective["fused_candidate_k"] == live.reranker_candidate_k
    assert effective["rrf_k"] == live.hybrid_rrf_k


def test_a_configured_similarity_floor_no_code_applies_is_reported_as_unapplied():
    live = config()
    assert live.min_similarity_threshold == 0.4

    effective = effective_retrieval_config(live, pipeline_active=True)

    assert effective["min_similarity_threshold_applied"] is None


def test_retrieval_eval_reaches_reranking_but_not_graph_only_stages():
    """A retrieval-only run issues one `search_chunks` call. Recording the
    merge cap, the pass-two thresholds and the answer-context depth would
    describe three stages it never entered."""
    live = config()

    effective = effective_retrieval_config(live, pipeline_active=False)

    assert effective["reranker_implementation"] == "sentence_transformers_cross_encoder"
    assert effective["context_k"] is None
    assert effective["merge_kept_k"] is None
    assert effective["pass_two_active"] is False
    assert effective["pass_two_chunk_threshold"] is None
    assert effective["pass_two_score_threshold"] is None
    assert effective["retrieval_strategy"] == "hybrid"


def test_the_pipeline_stage_settings_mirror_the_graph_when_it_runs():
    live = config()

    effective = effective_retrieval_config(live, pipeline_active=True)

    assert effective["context_k"] == live.top_k_documents
    assert effective["merge_kept_k"] == live.reranker_candidate_k
    assert effective["pass_two_active"] is True
    assert effective["pass_two_chunk_threshold"] == live.pass_two_chunk_threshold
    assert effective["pass_two_score_threshold"] == live.pass_two_score_threshold


def test_regular_pipeline_reports_no_extended_merge_or_second_pass():
    live = config()
    effective = effective_retrieval_config(
        live, pipeline_active=True, pipeline_mode="regular"
    )

    assert effective["reranker_active"] is True
    assert effective["context_k"] == live.top_k_documents
    assert effective["merge_kept_k"] is None
    assert effective["pass_two_active"] is False


def test_every_returned_key_is_declared_so_callers_can_exempt_its_nulls():
    """`EFFECTIVE_RETRIEVAL_FIELDS` is what lets `build_config_snapshot` and
    the benchmark manifest keep these nulls out of `unobserved`. If a new
    field were added without listing it, that field's null would silently
    start reading as "rag could not see this"."""
    for pipeline_active in (True, False):
        keys = set(effective_retrieval_config(config(), pipeline_active=pipeline_active))
        assert keys == set(EFFECTIVE_RETRIEVAL_FIELDS)
