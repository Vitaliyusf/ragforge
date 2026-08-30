"""What a deleted memory is allowed to do next: nothing.

MEMORY-EVAL-01 measured 24 of 24 deleted facts coming back the moment the same
canonical fact was proposed again, and every one of them then answered a query
it had no business answering. Deletion is therefore not a state a memory sits
in — it is a durable identity that outlives the row, the vector point, and the
process that wrote it.

Supersession is the opposite case and is deliberately kept apart: a fact that
stopped being current has a legitimate successor, and nothing here may block it.
"""

from unittest.mock import Mock

import pytest

from shared.context import bound_context

from app.agent.memory_agent import AgentScope, MemoryAgent, RetryBudgets
from app.tests._memory_harness import (
    FakeVectorIndex,
    build_memory_service,
    build_reconciliation_service,
    episodic_candidate,
    preference_candidate,
)

IDENTITY = dict(tenant_id="tenant-a", user_id="user-1", role="user")
OTHER_TENANT = dict(tenant_id="tenant-b", user_id="user-1", role="user")
OTHER_USER = dict(tenant_id="tenant-a", user_id="user-2", role="user")

BETA = "The user launched the beta milestone."
OFFICE = "The user works from the Tel Aviv office."
OFFICE_REWORDED = "The user is based out of the Tel Aviv office building."

CONCISE = "The user explicitly prefers concise answers with citations."
CONCISE_REWORDED = "The user likes short, direct responses."


def _candidate(text=BETA, fact_key=None, scope=None):
    candidate = dict(episodic_candidate(text))
    if fact_key:
        candidate["fact_key"] = fact_key
    if scope:
        candidate["scope"] = scope
    return candidate


def _write(service, identity, request_id, **kwargs):
    with bound_context(**identity):
        return service.write_memory(
            _candidate(**kwargs),
            {"owner_type": "user", "request_id": request_id},
        )


def _delete(service, identity, memory_id):
    with bound_context(**identity):
        return service.delete_memory(memory_id)


def _preference(text=CONCISE, preference_key="response_style", value="concise"):
    candidate = dict(preference_candidate(text))
    candidate["preference_key"] = preference_key
    candidate["value"] = value
    return candidate


def _write_preference(service, identity, request_id, **kwargs):
    with bound_context(**identity):
        return service.write_memory(
            _preference(**kwargs),
            {"owner_type": "user", "request_id": request_id},
        )


def _seed_and_delete_preference(service, identity=IDENTITY, request_id="req-pref-seed", **kwargs):
    written = _write_preference(service, identity, request_id, **kwargs)
    _delete(service, identity, written["memory_id"])
    return written


def _tombstones(database):
    return database["memory_deletion_tombstones"].docs


def _seed_and_delete(service, identity=IDENTITY, request_id="req-res-seed", **kwargs):
    written = _write(service, identity, request_id, **kwargs)
    _delete(service, identity, written["memory_id"])
    return written


# ----------------------------------------------------------------------
# The measured defect
# ----------------------------------------------------------------------


def test_the_same_exact_fact_is_not_recreated_after_a_delete():
    service, database, _ = build_memory_service()
    deleted = _seed_and_delete(service)

    again = _write(service, IDENTITY, "req-res-1")

    assert again["status"] == "rejected"
    assert again["outcome"] == "resurrection_suppressed"
    assert again["tombstone_match"] == "exact_content_same_scope"
    assert again["memory_id"] is None
    assert again["restore_allowed"] is False
    assert database["episodic_memories"].docs == []
    assert [doc["memory_id"] for doc in _tombstones(database)] == [deleted["memory_id"]]


def test_the_same_fact_slot_in_the_same_scope_is_suppressed_even_when_reworded():
    service, database, _ = build_memory_service()
    scope = {"context": "work"}
    _seed_and_delete(service, text=OFFICE, fact_key="office_city", scope=scope)

    again = _write(
        service,
        IDENTITY,
        "req-res-2",
        text=OFFICE_REWORDED,
        fact_key="office_city",
        scope=scope,
    )

    assert again["status"] == "rejected"
    assert again["tombstone_match"] == "fact_key_same_scope"
    assert database["episodic_memories"].docs == []


def test_the_same_fact_slot_in_a_different_scope_still_coexists():
    service, database, _ = build_memory_service()
    _seed_and_delete(service, text=OFFICE, fact_key="office_city", scope={"context": "work"})

    elsewhere = _write(
        service,
        IDENTITY,
        "req-res-3",
        text="The user works from the Haifa office.",
        fact_key="office_city",
        scope={"context": "personal"},
    )

    stored = database["episodic_memories"].docs
    assert elsewhere["status"] == "accepted"
    assert [doc["id"] for doc in stored] == [elsewhere["memory_id"]]
    assert stored[0]["scope"] == {"context": "personal"}


def test_supersession_is_not_deletion_and_the_new_current_fact_is_kept():
    service, database, _ = build_memory_service()
    original = _write(service, IDENTITY, "req-res-4", text="The user shipped the beta on the first of March.")

    replacement = _candidate("The user shipped the beta on the third of March.")
    replacement["supersedes"] = original["memory_id"]
    with bound_context(**IDENTITY):
        result = service.write_memory(replacement, {"owner_type": "user", "request_id": "req-res-5"})

    docs = {doc["id"]: doc for doc in database["episodic_memories"].docs}
    assert result["status"] == "accepted"
    assert docs[original["memory_id"]]["status"] == "superseded"
    assert docs[result["memory_id"]]["status"] == "active"
    assert _tombstones(database) == []


def test_a_deleted_memory_never_answers_a_query_again():
    service, _, _ = build_memory_service()
    _seed_and_delete(service)
    _write(service, IDENTITY, "req-res-6")

    with bound_context(**IDENTITY):
        retrieved = service.get_relevant_memories({"text": "beta milestone", "limit": 10})

    assert retrieved["memories"] == []


# ----------------------------------------------------------------------
# Reconciliation
# ----------------------------------------------------------------------


def test_reconciliation_removes_the_stale_point_and_never_restores_the_memory():
    index = FakeVectorIndex(enabled=True, fail_delete=True)
    service, database, _ = build_memory_service(index_client=index)
    deleted = _seed_and_delete(service)

    with bound_context(**IDENTITY):
        # The row survives only because the point did; both go on the retry.
        assert database["episodic_memories"].docs[0]["status"] == "deleted"
        index.fail_delete = False
        report = build_reconciliation_service(service).reconcile()

    assert report["repaired"] == 1
    assert index.deleted_ids == [deleted["memory_id"]]
    assert database["episodic_memories"].docs == []
    assert index.indexed_ids == [deleted["memory_id"]]
    assert len(_tombstones(database)) == 1

    again = _write(service, IDENTITY, "req-res-7")
    assert again["status"] == "rejected"


def test_reconciliation_finishes_a_delete_the_canonical_row_never_heard_about():
    # The identity was committed and then the process died: the row is still
    # active and still indexed. The identity, not the row, decides.
    index = FakeVectorIndex(enabled=True)
    service, database, _ = build_memory_service(index_client=index)
    written = _write(service, IDENTITY, "req-res-8")
    with bound_context(**IDENTITY):
        service._store_deletion_tombstone(database["episodic_memories"].docs[0])
        report = build_reconciliation_service(service).reconcile()

    assert report["drift"]["tombstone_vector"] == 1
    assert index.deleted_ids == [written["memory_id"]]
    assert database["episodic_memories"].docs == []


def test_repeated_reconciliation_over_a_deleted_fact_does_nothing_further():
    index = FakeVectorIndex(enabled=True)
    service, database, _ = build_memory_service(index_client=index)
    _seed_and_delete(service)

    with bound_context(**IDENTITY):
        second = build_reconciliation_service(service).reconcile()

    assert second["repaired"] == 0
    assert second["drift"] == {name: 0 for name in second["drift"]}
    assert len(_tombstones(database)) == 1


# ----------------------------------------------------------------------
# Retries and restarts
# ----------------------------------------------------------------------


def test_deleting_an_already_deleted_memory_reports_the_same_outcome():
    service, database, _ = build_memory_service()
    deleted = _seed_and_delete(service)

    retry = _delete(service, IDENTITY, deleted["memory_id"])

    assert retry["status"] == "deleted"
    assert retry["already_deleted"] is True
    assert retry["reconciliation_required"] is False
    assert len(_tombstones(database)) == 1


def test_an_unknown_memory_id_is_still_a_not_found_error():
    service, _, _ = build_memory_service()

    with pytest.raises(ValueError):
        _delete(service, IDENTITY, "never-existed")


def test_every_retry_of_the_rejected_write_stays_rejected():
    service, database, _ = build_memory_service()
    _seed_and_delete(service)

    outcomes = [_write(service, IDENTITY, f"req-res-retry-{attempt}")["status"] for attempt in range(3)]
    replay = _write(service, IDENTITY, "req-res-retry-0")

    assert outcomes == ["rejected", "rejected", "rejected"]
    assert replay["status"] == "rejected"
    assert database["episodic_memories"].docs == []


def test_a_restarted_service_over_the_same_storage_still_refuses_the_fact():
    service, database, _ = build_memory_service()
    _seed_and_delete(service)

    restarted, _, _ = build_memory_service()
    restarted._db_provider = lambda: database

    again = _write(restarted, IDENTITY, "req-res-9")

    assert again["status"] == "rejected"
    assert database["episodic_memories"].docs == []


# ----------------------------------------------------------------------
# Isolation
# ----------------------------------------------------------------------


def test_one_tenants_deletion_says_nothing_about_another_tenants_fact():
    service, database, _ = build_memory_service()
    _seed_and_delete(service)

    elsewhere = _write(service, OTHER_TENANT, "req-res-10")

    assert elsewhere["status"] == "accepted"
    assert [doc["tenant_id"] for doc in database["episodic_memories"].docs] == ["tenant-b"]


def test_one_users_deletion_says_nothing_about_another_users_fact():
    service, database, _ = build_memory_service()
    _seed_and_delete(service)

    elsewhere = _write(service, OTHER_USER, "req-res-11")

    assert elsewhere["status"] == "accepted"
    assert [doc["owner_user_id"] for doc in database["episodic_memories"].docs] == ["user-2"]


# ----------------------------------------------------------------------
# The Memory Agent has no way around any of this
# ----------------------------------------------------------------------


def _agent(service, actions):
    llm = Mock(side_effect=[{"actions": actions, "summary": "resurrection attempt"}])
    return MemoryAgent(service, llm, Mock(), retry_budgets=RetryBudgets())


def _scope():
    return AgentScope(
        tenant_id="tenant-a",
        user_id="user-1",
        role="user",
        request_id="req-res-agent",
        trace_id="trace-1",
        chat_id="chat-1",
        delete_authorized=False,
    )


def test_an_agent_proposal_to_recreate_a_deleted_memory_is_refused_by_persistence():
    service, database, _ = build_memory_service()
    _seed_and_delete(service)
    agent = _agent(service, [{"action": "create", "content": BETA, "confidence": 0.9}])

    with bound_context(**IDENTITY):
        result = agent.curate(
            [{"role": "user", "content": "Remember that I launched the beta milestone."}],
            [],
            _scope(),
            timeout=1.0,
        )

    # The model was allowed to propose it; the deterministic layer refused it.
    assert result.status == "success"
    assert [mutation["result"]["status"] for mutation in result.mutations] == ["rejected"]
    assert result.mutations[0]["result"]["outcome"] == "resurrection_suppressed"
    assert database["episodic_memories"].docs == []


def test_an_agent_supersede_aimed_at_a_deleted_memory_cannot_bring_it_back():
    service, database, _ = build_memory_service()
    deleted = _seed_and_delete(service)
    surviving = _write(service, IDENTITY, "req-res-12", text="The user hired a second backend engineer.")
    agent = _agent(
        service,
        [{
            "action": "supersede",
            "memory_id": deleted["memory_id"],
            "content": "The user launched the beta milestone last quarter.",
            "confidence": 0.9,
        }],
    )
    candidates = [{
        "id": deleted["memory_id"],
        "content": {"text": BETA},
        "tenant_id": "tenant-a",
        "owner_id": "user-1",
    }]

    with bound_context(**IDENTITY):
        result = agent.curate(
            [{"role": "user", "content": "Actually the beta launched last quarter."}],
            candidates,
            _scope(),
            timeout=1.0,
        )

    assert [mutation["result"]["status"] for mutation in result.mutations] == ["rejected"]
    assert result.mutations[0]["result"]["tombstone_match"] == "supersedes_deleted_memory"
    assert [doc["id"] for doc in database["episodic_memories"].docs] == [surviving["memory_id"]]


# ----------------------------------------------------------------------
# A preference key is the preference's identity
# ----------------------------------------------------------------------


def test_a_deleted_preference_key_is_not_recreated_under_different_wording():
    # A preference key holds exactly one authoritative value, so deleting it
    # deletes the slot rather than one particular sentence describing it.
    service, database, _ = build_memory_service()
    _seed_and_delete_preference(service)

    again = _write_preference(
        service,
        IDENTITY,
        "req-pref-1",
        text=CONCISE_REWORDED,
        value="short",
    )

    assert again["status"] == "rejected"
    assert again["outcome"] == "resurrection_suppressed"
    assert again["tombstone_match"] == "preference_key_same_owner"
    assert again["restore_allowed"] is False
    assert database["semantic_preferences"].docs == []


def test_deleting_one_preference_key_leaves_every_other_key_writable():
    service, database, _ = build_memory_service()
    _seed_and_delete_preference(service)

    other = _write_preference(
        service,
        IDENTITY,
        "req-pref-2",
        text="The user always wants sources cited.",
        preference_key="citations",
        value="always",
    )

    stored = database["semantic_preferences"].docs
    assert other["status"] == "accepted"
    assert [doc["preference_key"] for doc in stored] == ["citations"]


def test_one_tenants_deleted_preference_key_says_nothing_about_anothers():
    service, database, _ = build_memory_service()
    _seed_and_delete_preference(service)

    elsewhere = _write_preference(service, OTHER_TENANT, "req-pref-3")

    assert elsewhere["status"] == "accepted"
    assert [doc["tenant_id"] for doc in database["semantic_preferences"].docs] == ["tenant-b"]


def test_one_users_deleted_preference_key_says_nothing_about_anothers():
    service, database, _ = build_memory_service()
    _seed_and_delete_preference(service)

    elsewhere = _write_preference(service, OTHER_USER, "req-pref-4")

    assert elsewhere["status"] == "accepted"
    assert [doc["owner_user_id"] for doc in database["semantic_preferences"].docs] == ["user-2"]


# ----------------------------------------------------------------------
# What the deletion identity is allowed to keep
# ----------------------------------------------------------------------


def test_the_deletion_identity_keeps_no_memory_text_and_is_not_retrievable():
    service, database, _ = build_memory_service()
    _seed_and_delete(service, text=OFFICE, fact_key="office_city", scope={"context": "work"})

    tombstone = _tombstones(database)[0]

    assert set(tombstone) == {
        "memory_id",
        "owner_id",
        "owner_type",
        "memory_class",
        "content_hash",
        "fact_key",
        "preference_key",
        "scope_key",
        "deleted_at",
        "deletion_provenance",
        "revision",
        "tenant_id",
        "owner_user_id",
        "owner_admin_id",
    }
    assert tombstone["deletion_provenance"] == "explicit_delete"
    with bound_context(**IDENTITY):
        assert service.get_all_memories() == []
        assert service.get_relevant_memories({"text": "Tel Aviv office", "limit": 10})["memories"] == []


def test_the_preference_deletion_identity_keeps_the_key_but_no_preference_text():
    service, database, _ = build_memory_service()
    _seed_and_delete_preference(service)

    tombstone = _tombstones(database)[0]

    assert tombstone["memory_class"] == "semantic_preference"
    assert tombstone["preference_key"] == "response_style"
    assert tombstone["fact_key"] is None
    serialized = repr(tombstone)
    assert CONCISE not in serialized
    assert "concise" not in serialized
    with bound_context(**IDENTITY):
        assert service.get_all_memories() == []
