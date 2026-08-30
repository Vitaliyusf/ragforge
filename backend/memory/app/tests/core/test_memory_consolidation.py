"""The rules that decide what a new memory does to the ones already stored.

The policy is tested directly rather than only through the service because
its whole value is being replayable: the same candidate and the same
comparable memories must always produce the same outcome, and every rule that
refuses to guess has to be pinned down as deliberate.
"""

from app.services.memory_consolidation import (
    COMPARISON_SEMANTIC,
    OUTCOME_COEXIST,
    OUTCOME_CREATE,
    OUTCOME_DUPLICATE_EXACT,
    OUTCOME_DUPLICATE_SEMANTIC,
    OUTCOME_HISTORICAL,
    OUTCOME_NEEDS_REVIEW,
    OUTCOME_SUPERSEDE,
    ConsolidationPolicy,
    scope_key,
)


def _policy():
    return ConsolidationPolicy(duplicate_threshold=0.92, conflict_threshold=0.75)


def _memory(memory_id, *, content_hash="hash-a", scope=None, fact_key=None):
    return {
        "id": memory_id,
        "content_hash": content_hash,
        "scope": scope or {},
        "fact_key": fact_key,
    }


def _candidate(*, content_hash="hash-new", scope=None, fact_key=None, **extra):
    candidate = {"content_hash": content_hash, "scope": scope or {}, "fact_key": fact_key}
    candidate.update(extra)
    return candidate


def test_scope_key_is_order_and_case_independent():
    assert scope_key({"Environment": "New", "region": "EU"}) == scope_key({"region": "eu", "environment": "new"})
    assert scope_key(None) == ""
    assert scope_key({}) == ""


def test_identical_content_is_an_exact_duplicate_whatever_the_similarity_says():
    decision = _policy().decide(
        _candidate(content_hash="same"),
        [(_memory("existing-1", content_hash="same"), 0.1)],
    )

    assert decision.outcome == OUTCOME_DUPLICATE_EXACT
    assert decision.target_id == "existing-1"


def test_identical_content_in_another_scope_remains_a_coexisting_fact():
    decision = _policy().decide(
        _candidate(content_hash="same", scope={"environment": "new"}),
        [(_memory("existing-1", content_hash="same", scope={"environment": "legacy"}), 1.0)],
    )

    assert decision.outcome == OUTCOME_COEXIST


def test_an_explicitly_named_predecessor_outranks_every_inferred_rule():
    decision = _policy().decide(
        _candidate(supersedes="existing-1"),
        [(_memory("existing-1"), 0.1)],
    )

    assert decision.outcome == OUTCOME_SUPERSEDE
    assert decision.target_id == "existing-1"


def test_a_named_predecessor_outside_the_compared_bound_is_still_the_target():
    decision = _policy().decide(_candidate(supersedes="existing-9"), [])

    assert decision.outcome == OUTCOME_SUPERSEDE
    assert decision.target_id == "existing-9"


def test_a_candidate_written_with_an_end_of_validity_is_history():
    decision = _policy().decide(
        _candidate(valid_to="2026-01-01T00:00:00+00:00"),
        [(_memory("existing-1"), 0.99)],
    )

    assert decision.outcome == OUTCOME_HISTORICAL


def test_a_near_identical_memory_in_the_same_scope_is_a_semantic_duplicate():
    decision = _policy().decide(
        _candidate(),
        [(_memory("existing-1"), 0.95)],
        comparison=COMPARISON_SEMANTIC,
    )

    assert decision.outcome == OUTCOME_DUPLICATE_SEMANTIC
    assert decision.target_id == "existing-1"
    assert decision.comparison == COMPARISON_SEMANTIC


def test_a_near_identical_memory_in_another_scope_is_not_a_duplicate():
    decision = _policy().decide(
        _candidate(scope={"environment": "new"}),
        [(_memory("existing-1", scope={"environment": "legacy"}), 0.95)],
    )

    assert decision.outcome == OUTCOME_COEXIST


def test_a_new_value_for_the_same_declared_fact_supersedes_it():
    decision = _policy().decide(
        _candidate(fact_key="deployment_target"),
        [(_memory("existing-1", fact_key="deployment_target"), 0.8)],
    )

    assert decision.outcome == OUTCOME_SUPERSEDE
    assert decision.target_id == "existing-1"


def test_a_declared_fact_key_outranks_a_more_similar_unrelated_candidate():
    decision = _policy().decide(
        _candidate(fact_key="deployment_target"),
        [
            (_memory("unrelated"), 0.99),
            (_memory("old-value", fact_key="deployment_target"), 0.05),
        ],
        comparison=COMPARISON_SEMANTIC,
    )

    assert decision.outcome == OUTCOME_SUPERSEDE
    assert decision.target_id == "old-value"


def test_similar_memories_with_no_declared_fact_are_kept_and_flagged():
    decision = _policy().decide(
        _candidate(),
        [(_memory("existing-1"), 0.8)],
    )

    # Nothing here says the two are the same fact, and similarity alone is not
    # allowed to retire a memory or merge one into another.
    assert decision.outcome == OUTCOME_NEEDS_REVIEW
    assert decision.target_id == "existing-1"


def test_different_declared_facts_do_not_supersede_each_other():
    decision = _policy().decide(
        _candidate(fact_key="deployment_target"),
        [(_memory("existing-1", fact_key="database_engine"), 0.8)],
    )

    assert decision.outcome == OUTCOME_NEEDS_REVIEW


def test_an_unrelated_memory_leaves_the_candidate_a_plain_creation():
    decision = _policy().decide(
        _candidate(),
        [(_memory("existing-1"), 0.2)],
    )

    assert decision.outcome == OUTCOME_CREATE


def test_no_comparable_memory_is_a_plain_creation():
    decision = _policy().decide(_candidate(), [])

    assert decision.outcome == OUTCOME_CREATE
    assert decision.candidates_considered == 0


def test_the_decision_is_the_same_whatever_order_the_candidates_arrive_in():
    policy = _policy()
    comparable = [
        (_memory("existing-b", fact_key="deployment_target"), 0.80),
        (_memory("existing-a", fact_key="deployment_target"), 0.80),
        (_memory("existing-c", fact_key="deployment_target"), 0.79),
    ]

    forward = policy.decide(_candidate(fact_key="deployment_target"), comparable)
    reversed_order = policy.decide(_candidate(fact_key="deployment_target"), list(reversed(comparable)))

    assert forward.outcome == reversed_order.outcome
    assert forward.target_id == reversed_order.target_id == "existing-a"


def test_the_decision_records_what_it_compared_against():
    decision = _policy().decide(
        _candidate(),
        [(_memory("existing-1"), 0.3), (_memory("existing-2"), 0.2)],
        comparison=COMPARISON_SEMANTIC,
    )
    provenance = decision.as_provenance()

    assert provenance["comparison"] == COMPARISON_SEMANTIC
    assert provenance["candidates_considered"] == 2
    assert provenance["related_ids"] == ["existing-1", "existing-2"]
    assert provenance["outcome"] == OUTCOME_CREATE


def test_a_scoped_candidate_is_compared_against_its_own_scope_first():
    # The globally most similar memory is the one in the other scope. A
    # candidate must still be judged against the scope it belongs to,
    # otherwise it retires a fact that was never about the same context.
    decision = _policy().decide(
        _candidate(scope={"environment": "new"}, fact_key="deployment_target"),
        [
            (_memory("global-1", fact_key="deployment_target"), 0.90),
            (_memory("scoped-1", scope={"environment": "new"}, fact_key="deployment_target"), 0.80),
        ],
    )

    assert decision.outcome == OUTCOME_SUPERSEDE
    assert decision.target_id == "scoped-1"


def test_a_related_memory_only_in_another_scope_leaves_both_valid():
    decision = _policy().decide(
        _candidate(scope={"environment": "new"}),
        [(_memory("global-1"), 0.85)],
    )

    assert decision.outcome == OUTCOME_COEXIST
    assert decision.target_id == "global-1"
