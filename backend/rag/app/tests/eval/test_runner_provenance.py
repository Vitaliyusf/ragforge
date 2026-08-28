"""What a run records about the configuration and dataset it scored."""
from __future__ import annotations



from shared.context import bound_context

from app.tests.eval._harness import (
    ADMIN,
    build,
    execute,
    fetch,
)

def test_the_run_captures_a_config_snapshot_naming_what_it_cannot_see():
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    snapshot = fetch(store, run["run_id"])["config_snapshot"]

    assert snapshot["top_k_documents"] == 6
    # Recorded separately from the production depth: the run's ranking was
    # drawn from twenty candidates, not from the six an answer is built from.
    assert snapshot["candidate_k"] == 20
    assert snapshot["retrieval_strategy"] == "dense_vector"
    # Not stored as a silent null: a diff must not read two unknown embedding
    # models as a match.
    assert "embedding_model" in snapshot["unobserved"]
    assert "chunk_size" in snapshot["unobserved"]


def test_a_retrieval_run_cannot_claim_a_reranker_a_legacy_flag_turned_on():
    """The acceptance criterion at the run level. `reranker_enabled` and
    `hybrid_search_enabled` default to true and nothing in the request path
    reads either, so a run must not report them as what produced its
    numbers."""
    store, runner, _, dataset_id = build()
    assert runner.config.reranker_enabled is True
    assert runner.config.hybrid_search_enabled is True

    run = execute(runner, dataset_id)
    snapshot = fetch(store, run["run_id"])["config_snapshot"]

    assert snapshot["reranker_active"] is False
    assert snapshot["reranker_model"] is None
    assert snapshot["hybrid_search_active"] is False
    for legacy in (
        "reranker_enabled",
        "reranker_top_k",
        "hybrid_search_enabled",
        "hybrid_search_alpha",
        "min_similarity_threshold",
    ):
        assert legacy not in snapshot


def test_a_retrieval_run_records_no_stage_it_never_reached():
    """It issues one `search_chunks` call: no merge, no pass two, no answer
    context. The production values for those would name work it never did."""
    store, runner, _, dataset_id = build()

    run = execute(runner, dataset_id)
    snapshot = fetch(store, run["run_id"])["config_snapshot"]

    assert snapshot["context_k"] is None
    assert snapshot["merge_kept_k"] is None
    assert snapshot["pass_two_active"] is False
    assert snapshot["pass_two_score_threshold"] is None
    # None of those nulls is a gap in what rag could see, so none of them may
    # appear alongside the env-sourced fields that genuinely are.
    for field in ("context_k", "merge_kept_k", "reranker_model"):
        assert field not in snapshot["unobserved"]



def test_the_run_snapshots_the_dataset_version_and_fingerprint():
    """`dataset_id` alone cannot prove which labels a run scored: the items
    behind it can be replaced. The run copies the pair at start."""
    store, runner, _, dataset_id = build()
    with bound_context(**ADMIN.to_dict()):
        dataset = store.get_dataset(dataset_id)

    run = execute(runner, dataset_id)
    stored = fetch(store, run["run_id"])

    assert stored["dataset_version"] == dataset["dataset_version"] == 1
    assert stored["dataset_sha256"] == dataset["dataset_sha256"]


def test_relabelling_a_dataset_does_not_rewrite_what_past_runs_scored():
    """The regression evidence has to stay evidence. An edit after a run
    moves the dataset forward and leaves the finished run describing the
    labels it actually used."""
    store, runner, _, dataset_id = build()
    first = fetch(store, execute(runner, dataset_id)["run_id"])

    with bound_context(**ADMIN.to_dict()):
        store.update_dataset(
            dataset_id,
            items=[{"query": "first", "relevant_chunk_ids": ["relabelled"]}],
        )
    second = fetch(store, execute(runner, dataset_id)["run_id"])
    unchanged = fetch(store, first["run_id"])

    assert unchanged["dataset_version"] == first["dataset_version"] == 1
    assert unchanged["dataset_sha256"] == first["dataset_sha256"]
    assert second["dataset_version"] == 2
    assert second["dataset_sha256"] != first["dataset_sha256"]


# ── Failure paths ─────────────────────────────────────────────────────────


