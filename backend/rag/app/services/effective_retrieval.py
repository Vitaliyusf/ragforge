"""What the retrieval pipeline actually does, as opposed to what config claims.

``RAGConfig`` carries a block its own comment marks "Legacy fields retained
for compatibility": ``reranker_enabled``, ``reranker_top_k``,
``hybrid_search_enabled``, ``hybrid_search_alpha``. They default to true and
nothing reads them. ``min_similarity_threshold`` is in the same position — a
0.4 floor no code applies. Copying those values into a run's provenance made
every eval run and every benchmark manifest report a reranker and a hybrid
retriever that were never in the request path, which is the one thing a
provenance record must not do: a number produced *without* a reranker,
labelled as produced *with* one, misdirects every tuning decision taken from
it afterwards.

This module is the single place that answers "what ran", so the eval config
snapshot and the benchmark manifest cannot drift apart on it. What it reports
is derived from the implementation, verified against it, and named here:

- **Retrieval is dense-vector only.** ``ConversationBackendClient.search_chunks``
  embeds the query and sends ``query_vector``/``top_k`` to ``vector_db``. No
  lexical arm, no fusion weight, no ``alpha`` in the payload — so hybrid
  search is inactive and its alpha is applied to nothing.
- **No reranker model exists.** ``ConversationGraphRunner._rerank_and_merge``
  de-duplicates candidates by ``chunk_id``, keeps the higher vector score of
  each, sorts by that same score and caps the list at
  ``top_k_documents * 2``. It re-orders nothing the vector store did not
  already order, and no second model scores a candidate. It is a merge, and
  it is reported as one, with ``reranker_model`` null because there is none.
- **A retrieval-only eval run never reaches the graph.** It issues one
  ``search_chunks`` call, so the merge stage, pass two and the answer context
  are not part of what it measured and are reported as null rather than as
  the production settings it never exercised.

**Every null in this block is observed, never unknown.** That is the opposite
of the env-sourced fields in :func:`app.services.eval_store.build_config_snapshot`
and :func:`app.services.benchmark_manifest.build_benchmark_manifest`, where
null means "rag could not see it" and the field is named in ``unobserved``.
Here a null is a positive finding — "no reranker model", "this run never
built an answer context" — so :data:`EFFECTIVE_RETRIEVAL_FIELDS` exists to
let those two callers keep it out of their ``unobserved`` lists. A reader
that conflated the two would turn "provably absent" back into "unknown".

Descriptive only: nothing in the retrieval or eval path branches on what this
returns, so it can never be the reason a run behaves differently.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# The only strategy the request path implements. A literal rather than a
# config read: config cannot currently express another one, and reading a
# field that does not exist to describe behavior that cannot vary would
# recreate exactly the legacy-flag problem this module was written for.
RETRIEVAL_STRATEGY_DENSE_VECTOR = "dense_vector"

# What `_rerank_and_merge` is. Named for what it does — de-duplicate, keep the
# better vector score, sort by it — so nobody reads "reranker" into a stage
# that applies no model of its own.
MERGE_IMPLEMENTATION_SCORE_ORDER = "score_order_merge"

# How much wider than the answer context the merge keeps, mirroring the
# `top_k_documents * 2` cap in `ConversationGraphRunner._rerank_and_merge`.
MERGE_KEPT_MULTIPLIER = 2

# Every key :func:`effective_retrieval_config` returns. Callers that maintain
# an `unobserved` list must exempt these: a null here is a finding, not a gap.
EFFECTIVE_RETRIEVAL_FIELDS = frozenset(
    {
        "retrieval_strategy",
        "hybrid_search_active",
        "hybrid_search_alpha_applied",
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
    """Describe the retrieval the caller is about to perform, or performed.

    Args:
        config: Live rag configuration. Read for the thresholds the graph
            genuinely branches on; its legacy flags are deliberately ignored.
        pipeline_active: Whether the conversation graph runs. ``True`` for an
            ``end_to_end`` eval run and for a benchmark manifest describing
            the deployed pipeline; ``False`` for a retrieval-only eval run,
            whose single ``search_chunks`` call reaches neither the merge
            stage nor pass two nor answer generation.

    Returns:
        The keys in :data:`EFFECTIVE_RETRIEVAL_FIELDS`. Stage settings for
        stages the caller does not reach are ``None`` — observed absent, not
        unknown — and never the production values of a stage it skipped.
    """
    top_k: Optional[int] = getattr(config, "top_k_documents", None)
    return {
        "retrieval_strategy": RETRIEVAL_STRATEGY_DENSE_VECTOR,
        # Not `config.hybrid_search_enabled`. There is no lexical or sparse
        # arm to fuse with, so the flag describes an implementation that was
        # never built and the alpha weights nothing.
        "hybrid_search_active": False,
        "hybrid_search_alpha_applied": None,
        # Likewise not `config.reranker_enabled`. `reranker_top_k` is omitted
        # entirely rather than recorded as inactive: it is a depth for a
        # stage that does not exist, and the depth that does bound the merge
        # is `merge_kept_k`.
        "reranker_active": False,
        "reranker_implementation": (
            MERGE_IMPLEMENTATION_SCORE_ORDER if pipeline_active else None
        ),
        "reranker_model": None,
        # Configured but applied nowhere in rag or vector_db: no code drops a
        # candidate for scoring below it.
        "min_similarity_threshold_applied": None,
        # How many chunks an answer was actually built from. Null for a
        # retrieval-only run, which builds no answer context at all — the
        # candidate depth it *did* use is recorded separately as
        # `candidate_k`.
        "context_k": top_k if pipeline_active else None,
        "merge_kept_k": (
            top_k * MERGE_KEPT_MULTIPLIER
            if pipeline_active and isinstance(top_k, int)
            else None
        ),
        "pass_two_active": pipeline_active,
        "pass_two_chunk_threshold": (
            getattr(config, "pass_two_chunk_threshold", None) if pipeline_active else None
        ),
        "pass_two_score_threshold": (
            getattr(config, "pass_two_score_threshold", None) if pipeline_active else None
        ),
    }
