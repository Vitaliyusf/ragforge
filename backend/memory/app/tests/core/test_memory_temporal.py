"""Current truth, historical truth, and facts that validly disagree.

The worked example throughout is the one the architecture has to get right:
a project that used to deploy to GCP and now deploys to AWS. Both sentences
are true — one of them is true *now*, and only that distinction keeps a
retrieval system from confidently reporting last quarter's infrastructure.
"""

import pytest

from shared.context import bound_context

from app.core.config import settings
from app.tests._memory_harness import (
    BagOfWordsEmbeddingClient,
    InMemoryVectorIndex,
    build_memory_service,
)

IDENTITY = dict(tenant_id="tenant-a", user_id="user-1", role="user")

OLD_FACT = "The project deploys to GCP."
NEW_FACT = "The project deploys to AWS."


def _fact(text, *, fact_key=None, scope=None, event_at="2026-03-01T00:00:00+00:00", **extra):
    candidate = {
        "content": {"text": text},
        "event_at": event_at,
        "importance": 0.8,
        "confidence": 0.8,
        "provenance": {"explicit_user_signal": True},
    }
    if fact_key:
        candidate["fact_key"] = fact_key
    if scope:
        candidate["scope"] = scope
    candidate.update(extra)
    return candidate


def _service():
    return build_memory_service(
        index_client=InMemoryVectorIndex(),
        embedding_client=BagOfWordsEmbeddingClient(),
    )


def _write(service, candidate, request_id):
    with bound_context(**IDENTITY):
        return service.write_memory(candidate, {"owner_type": "user", "request_id": request_id})


def _query(service, text, **options):
    with bound_context(**IDENTITY):
        return service.get_relevant_memories({"text": text, "limit": 10, **options})


def test_a_new_value_for_a_declared_fact_closes_the_old_ones_validity():
    service, database, _ = _service()
    old = _write(service, _fact(OLD_FACT, fact_key="deployment_target"), "req-t-1")
    new = _write(
        service,
        _fact(NEW_FACT, fact_key="deployment_target", event_at="2026-04-01T00:00:00+00:00"),
        "req-t-2",
    )

    docs = {doc["id"]: doc for doc in database["episodic_memories"].docs}
    assert new["consolidation"]["outcome"] == "supersede"
    assert new["superseded_memory_id"] == old["memory_id"]
    # The old fact is not deleted. It keeps its text and gains the moment it
    # stopped being true.
    assert docs[old["memory_id"]]["status"] == "superseded"
    assert docs[old["memory_id"]]["valid_to"] == "2026-04-01T00:00:00+00:00"
    assert docs[old["memory_id"]]["content"]["text"] == OLD_FACT
    assert docs[new["memory_id"]]["valid_to"] is None


def test_a_declared_fact_is_not_lost_outside_the_semantic_candidate_bound(monkeypatch):
    monkeypatch.setattr(settings, "memory_dedupe_candidate_limit", 1)
    service, database, _ = _service()
    old = _write(
        service,
        _fact("The project deploys to GCP.", fact_key="deployment_target"),
        "req-t-bound-1",
    )
    _write(
        service,
        _fact("Hosting vendor documentation is now pending."),
        "req-t-bound-2",
    )

    replacement = _write(
        service,
        _fact("Hosting vendor is now AWS.", fact_key="deployment_target"),
        "req-t-bound-3",
    )

    stored_old = next(doc for doc in database["episodic_memories"].docs if doc["id"] == old["memory_id"])
    assert replacement["consolidation"]["outcome"] == "supersede"
    assert replacement["superseded_memory_id"] == old["memory_id"]
    assert stored_old["status"] == "superseded"


def test_a_current_query_answers_with_the_current_fact_only():
    service, _, _ = _service()
    _write(service, _fact(OLD_FACT, fact_key="deployment_target"), "req-t-3")
    _write(
        service,
        _fact(NEW_FACT, fact_key="deployment_target", event_at="2026-04-01T00:00:00+00:00"),
        "req-t-4",
    )

    returned = [memory["content"]["text"] for memory in _query(service, "where does the project deploy")["memories"]]

    assert returned == [NEW_FACT]


def test_history_is_retrievable_but_only_when_it_is_asked_for():
    service, _, _ = _service()
    _write(service, _fact(OLD_FACT, fact_key="deployment_target"), "req-t-5")
    _write(
        service,
        _fact(NEW_FACT, fact_key="deployment_target", event_at="2026-04-01T00:00:00+00:00"),
        "req-t-6",
    )

    result = _query(service, "where does the project deploy", include_history=True)
    memories = result["memories"]

    assert [memory["content"]["text"] for memory in memories] == [NEW_FACT, OLD_FACT]
    # The current fact is first because it is current, not because it scored
    # better — and each result says which it is.
    assert [memory["is_current"] for memory in memories] == [True, False]
    assert result["provenance"]["temporal"]["include_history"] is True


def test_a_historical_fact_cannot_outrank_the_current_one_on_similarity():
    service, _, _ = _service()
    _write(service, _fact(OLD_FACT, fact_key="deployment_target"), "req-t-7")
    _write(
        service,
        _fact(NEW_FACT, fact_key="deployment_target", event_at="2026-04-01T00:00:00+00:00"),
        "req-t-8",
    )

    # A query worded exactly like the retired memory: embedding similarity
    # points straight at the historical fact, and it still must not win.
    memories = _query(service, OLD_FACT, include_history=True)["memories"]

    assert memories[0]["content"]["text"] == NEW_FACT
    assert memories[0]["ranking"]["semantic_relevance"] < memories[1]["ranking"]["semantic_relevance"]


def test_as_of_answers_what_was_true_at_a_past_moment():
    service, _, _ = _service()
    _write(service, _fact(OLD_FACT, fact_key="deployment_target"), "req-t-9")
    _write(
        service,
        _fact(NEW_FACT, fact_key="deployment_target", event_at="2026-04-01T00:00:00+00:00"),
        "req-t-10",
    )

    returned = [
        memory["content"]["text"]
        for memory in _query(service, "where does the project deploy", as_of="2026-03-15T00:00:00+00:00")["memories"]
    ]

    # In March the migration had not happened yet, so GCP is the answer and
    # AWS — written later but valid from April — is not yet current.
    assert OLD_FACT in returned


def test_facts_in_different_scopes_coexist_instead_of_replacing_each_other():
    service, database, _ = _service()
    _write(service, _fact(OLD_FACT, fact_key="deployment_target"), "req-t-11")
    scoped = _write(
        service,
        _fact(NEW_FACT, fact_key="deployment_target", scope={"environment": "new"}),
        "req-t-12",
    )

    active = [doc for doc in database["episodic_memories"].docs if doc["status"] == "active"]
    assert scoped["consolidation"]["outcome"] == "coexist"
    assert len(active) == 2
    assert all(doc["valid_to"] is None for doc in active)


def test_a_scoped_query_answers_from_its_own_scope():
    service, _, _ = _service()
    _write(service, _fact(OLD_FACT, fact_key="deployment_target"), "req-t-13")
    _write(
        service,
        _fact(NEW_FACT, fact_key="deployment_target", scope={"environment": "new"}),
        "req-t-14",
    )

    scoped = _query(service, "where does the project deploy", scope={"environment": "new"})
    global_scope = _query(service, "where does the project deploy", scope={})

    assert [memory["content"]["text"] for memory in scoped["memories"]] == [NEW_FACT]
    assert [memory["content"]["text"] for memory in global_scope["memories"]] == [OLD_FACT]
    assert scoped["provenance"]["scope"]["scope"] == "environment=new"


def test_a_fact_written_as_history_never_becomes_the_current_answer():
    service, _, _ = _service()
    _write(service, _fact(NEW_FACT, fact_key="deployment_target"), "req-t-15")
    historical = _write(
        service,
        _fact(OLD_FACT, fact_key="deployment_target", valid_to="2026-02-01T00:00:00+00:00"),
        "req-t-16",
    )

    assert historical["consolidation"]["outcome"] == "historical"
    assert historical["is_current"] is False
    returned = [memory["content"]["text"] for memory in _query(service, "where does the project deploy")["memories"]]
    assert returned == [NEW_FACT]


@pytest.mark.parametrize("include_history", [False, True])
def test_temporal_retrieval_is_deterministic(include_history):
    service, _, _ = _service()
    _write(service, _fact(OLD_FACT, fact_key="deployment_target"), "req-t-17")
    _write(
        service,
        _fact(NEW_FACT, fact_key="deployment_target", event_at="2026-04-01T00:00:00+00:00"),
        "req-t-18",
    )

    first = _query(service, "deployment target", include_history=include_history)["memories"]
    second = _query(service, "deployment target", include_history=include_history)["memories"]

    assert [memory["id"] for memory in first] == [memory["id"] for memory in second]
