"""Tenant and user boundaries around long-term memory.

Every test here writes deliberately colliding data — same owner ids, same
memory text, same preference key — because a filter that only works while the
two sides look different is not a boundary.
"""

import pytest

from shared.context import bound_context

from app.tests._memory_harness import (
    FakeVectorIndex,
    build_memory_service,
    episodic_candidate,
    preference_candidate,
)


TENANT_A = dict(tenant_id="tenant-a", user_id="user-1", role="user")
TENANT_B = dict(tenant_id="tenant-b", user_id="user-1", role="user")
TENANT_A_OTHER_USER = dict(tenant_id="tenant-a", user_id="user-2", role="user")


def _write(service, identity, text, request_id):
    with bound_context(**identity):
        return service.write_memory(
            episodic_candidate(text),
            {"owner_type": "user", "request_id": request_id},
        )


def _retrieve(service, identity, text="beta milestone"):
    with bound_context(**identity):
        return service.get_relevant_memories({"text": text, "limit": 10})


def test_tenant_cannot_retrieve_another_tenants_memory():
    service, _, _ = build_memory_service()
    _write(service, TENANT_A, "Tenant A launched the beta milestone.", "req-iso-1")
    _write(service, TENANT_B, "Tenant B launched the beta milestone.", "req-iso-2")

    returned = [memory["content"]["text"] for memory in _retrieve(service, TENANT_A)["memories"]]

    assert returned == ["Tenant A launched the beta milestone."]


def test_user_cannot_retrieve_another_users_memory_in_the_same_tenant():
    service, _, _ = build_memory_service()
    _write(service, TENANT_A, "User one launched the beta milestone.", "req-iso-3")
    _write(service, TENANT_A_OTHER_USER, "User two launched the beta milestone.", "req-iso-4")

    returned = [memory["content"]["text"] for memory in _retrieve(service, TENANT_A)["memories"]]

    assert returned == ["User one launched the beta milestone."]


def test_identical_memory_text_across_tenants_is_stored_separately():
    service, database, _ = build_memory_service()
    same_text = "The user launched the beta milestone."

    first = _write(service, TENANT_A, same_text, "req-iso-5")
    second = _write(service, TENANT_B, same_text, "req-iso-6")

    # Identical content is a duplicate only inside one tenant/user scope; the
    # other tenant still gets its own memory.
    assert first["status"] == "accepted"
    assert second["status"] == "accepted"
    assert first["memory_id"] != second["memory_id"]
    assert len(database["episodic_memories"].docs) == 2
    assert len(_retrieve(service, TENANT_A)["memories"]) == 1


def test_a_preference_key_is_per_user_not_global():
    service, _, _ = build_memory_service()
    with bound_context(**TENANT_A):
        service.write_memory(
            preference_candidate("The user explicitly prefers concise answers."),
            {"owner_type": "user", "request_id": "req-iso-7"},
        )
    with bound_context(**TENANT_A_OTHER_USER):
        other = dict(preference_candidate("The other user explicitly prefers extended answers."))
        other["value"] = "extended"
        service.write_memory(other, {"owner_type": "user", "request_id": "req-iso-8"})

    with bound_context(**TENANT_A):
        mine = service.get_relevant_memories({"text": "answer length", "limit": 10})

    values = [memory.get("value") for memory in mine["memories"]]
    assert values == ["concise"]


def test_delete_cannot_reach_across_a_tenant_boundary():
    service, database, _ = build_memory_service()
    victim = _write(service, TENANT_B, "Tenant B launched the beta milestone.", "req-iso-9")

    with bound_context(**TENANT_A):
        with pytest.raises(ValueError):
            service.delete_memory(victim["memory_id"])

    assert len(database["episodic_memories"].docs) == 1


def test_update_cannot_reach_across_a_user_boundary():
    service, database, _ = build_memory_service()
    victim = _write(service, TENANT_A_OTHER_USER, "User two launched the beta.", "req-iso-10")

    with bound_context(**TENANT_A):
        with pytest.raises(ValueError):
            service.update_memory(victim["memory_id"], content="rewritten by another user")

    assert database["episodic_memories"].docs[0]["content"]["text"] == "User two launched the beta."


def test_supersession_cannot_retire_another_tenants_memory():
    service, database, _ = build_memory_service()
    victim = _write(service, TENANT_B, "Tenant B launched the beta milestone.", "req-iso-11")

    replacement = dict(episodic_candidate("Tenant A has its own milestone."))
    replacement["supersedes"] = victim["memory_id"]
    with bound_context(**TENANT_A):
        result = service.write_memory(replacement, {"owner_type": "user", "request_id": "req-iso-12"})

    docs = {doc["id"]: doc for doc in database["episodic_memories"].docs}
    assert result["superseded_memory_id"] is None
    assert docs[victim["memory_id"]]["status"] == "active"
    assert docs[victim["memory_id"]]["superseded_by"] is None


def test_debug_listing_stays_inside_the_callers_scope():
    service, _, _ = build_memory_service()
    _write(service, TENANT_A, "Tenant A launched the beta milestone.", "req-iso-13")
    _write(service, TENANT_B, "Tenant B launched the beta milestone.", "req-iso-14")

    with bound_context(**TENANT_A):
        listed = service.list_memory_for_debug({})
        all_memories = service.get_all_memories()

    assert [memory["content"]["text"] for memory in listed["memories"]] == [
        "Tenant A launched the beta milestone."
    ]
    assert len(all_memories) == 1


def test_vector_search_filters_are_reported_as_applied_scope():
    service, _, _ = build_memory_service(index_client=FakeVectorIndex(enabled=True))
    _write(service, TENANT_A, "Tenant A launched the beta milestone.", "req-iso-15")

    result = _retrieve(service, TENANT_A)

    scope = result["provenance"]["scope"]
    assert scope["tenant_scoped"] is True
    assert scope["user_scoped"] is True
    assert scope["owner_id"] == "user-1"
    assert scope["statuses"] == ["active"]
