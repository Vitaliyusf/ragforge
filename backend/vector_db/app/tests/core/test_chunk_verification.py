"""`verify_chunk_ids`: what it reports, and what it refuses to reveal.

It exists so the eval harness can tell a retrieval miss from a benchmark
label whose chunk no longer exists. It must never become a way to look
outside the caller's own tenant, so most of what follows is about what it
refuses rather than what it returns.
"""

import pytest

from app.core.constants import MAX_VERIFY_IDS
from app.core.errors import InvalidVectorError
from shared.auth import AuthError
from shared.context import bound_context

from app.tests._vector_harness import (
    ADMIN_A,
    ADMIN_B,
    build_chunk,
    seed,
)


"""`verify_chunk_ids`: what it reports, and what it refuses to reveal.

It exists so the eval harness can tell a retrieval miss from a benchmark
label whose chunk no longer exists. It must never become a way to look
outside the caller's own tenant, so most of what follows is about what it
refuses rather than what it returns.
"""


def test_an_existing_chunk_id_verifies_as_present_and_retrievable(live_service):
    seed(live_service, ADMIN_A, build_chunk(chunk_id="chunk-live"))

    with bound_context(**ADMIN_A):
        result = live_service.verify_chunk_ids(chunk_ids=["chunk-live"])

    assert result["chunk_ids"]["present"] == ["chunk-live"]
    assert result["chunk_ids"]["retrievable"] == ["chunk-live"]
    assert result["chunk_ids"]["missing"] == []


def test_a_deleted_chunk_id_verifies_as_missing(live_service):
    """The whole point: reindexing dropped the chunk the label names."""
    seed(live_service, ADMIN_A, build_chunk(chunk_id="chunk-gone"))
    with bound_context(**ADMIN_A):
        live_service.delete_chunks({"file_id": "file-1"})
        result = live_service.verify_chunk_ids(chunk_ids=["chunk-gone"])

    assert result["chunk_ids"]["missing"] == ["chunk-gone"]
    assert result["chunk_ids"]["present"] == []


def test_file_ids_are_verified_as_well_as_chunk_ids(live_service):
    """A file-level golden set labels files, and drifts the same way."""
    seed(live_service, ADMIN_A, build_chunk(chunk_id="chunk-1", file_id="file-kept"))

    with bound_context(**ADMIN_A):
        result = live_service.verify_chunk_ids(file_ids=["file-kept", "file-dropped"])

    assert result["file_ids"]["present"] == ["file-kept"]
    assert result["file_ids"]["missing"] == ["file-dropped"]
    # The chunk field was not asked about and reports nothing, rather than
    # borrowing the file answer.
    assert result["chunk_ids"] == {"present": [], "retrievable": [], "missing": []}


def test_another_tenants_chunk_id_is_indistinguishable_from_a_deleted_one(live_service):
    """Cross-tenant ids must not be verifiable - existence is information."""
    seed(
        live_service,
        ADMIN_B,
        build_chunk(
            chunk_id="chunk-b",
            tenant_id="tenant-b",
            owner_user_id="user-b",
            owner_admin_id="admin-b",
        ),
    )

    with bound_context(**ADMIN_A):
        result = live_service.verify_chunk_ids(chunk_ids=["chunk-b"])

    assert result["chunk_ids"]["missing"] == ["chunk-b"]
    assert result["chunk_ids"]["present"] == []


def test_verification_scope_comes_from_the_identity_not_the_payload(
    vector_service,
    mock_vector_store,
):
    """There is no filter argument to forge, and the scope is the caller's."""
    mock_vector_store.lookup_ids.return_value = {"present": [], "retrievable": []}

    with bound_context(**ADMIN_A):
        vector_service.verify_chunk_ids(chunk_ids=["c1"])

    field, values, filters = mock_vector_store.lookup_ids.call_args.args
    assert field == "chunk_id"
    assert values == ["c1"]
    assert filters == {"tenant_id": "tenant-a", "owner_admin_id": "admin-a"}


def test_verification_fails_closed_without_an_identity_in_production(
    vector_service,
    monkeypatch,
):
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    with pytest.raises(AuthError, match="identity is missing"):
        vector_service.verify_chunk_ids(chunk_ids=["c1"])


def test_verification_without_any_id_is_refused(vector_service):
    """An empty request is the one shape that would mean 'show me anything'."""
    with bound_context(**ADMIN_A):
        with pytest.raises(InvalidVectorError, match="chunk_ids, file_ids, or both"):
            vector_service.verify_chunk_ids()


def test_a_chunk_barred_from_retrieval_is_present_but_not_retrievable(live_service):
    """Neither a deleted label nor a reachable one - a third state."""
    seed(
        live_service,
        ADMIN_A,
        build_chunk(chunk_id="chunk-blocked", review_status="removed"),
    )

    with bound_context(**ADMIN_A):
        result = live_service.verify_chunk_ids(chunk_ids=["chunk-blocked"])

    assert result["chunk_ids"]["present"] == ["chunk-blocked"]
    assert result["chunk_ids"]["retrievable"] == []
    assert result["chunk_ids"]["missing"] == []


def test_lookup_ids_refuses_a_field_that_is_not_an_id(live_service):
    """`text` would turn an existence check into a content query."""
    with pytest.raises(ValueError, match="not a verifiable id field"):
        live_service.vector_store.lookup_ids("text", ["anything"])


def test_lookup_ids_refuses_more_ids_than_the_cap(live_service):
    with pytest.raises(ValueError, match="the limit is"):
        live_service.vector_store.lookup_ids(
            "chunk_id", [f"c{index}" for index in range(MAX_VERIFY_IDS + 1)]
        )
