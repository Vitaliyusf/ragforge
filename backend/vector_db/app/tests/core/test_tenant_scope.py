"""Tenant and ownership scoping: identity decides the filter, never the payload."""

import pytest

from shared.auth import AuthError
from shared.context import bound_context

from app.tests._vector_harness import (
    ADMIN_A,
    build_chunk,
)


"""Tenant and ownership scoping: identity decides the filter, never the payload."""


def test_user_search_overrides_client_tenant_and_owner_filters(vector_service, mock_vector_store):
    with bound_context(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    ):
        vector_service.search_chunks(
            [0.1, 0.2, 0.3],
            filters={"tenant_id": "tenant-b", "owner_user_id": "user-b", "file_id": "file-a"},
        )

    filters = mock_vector_store.search_chunks.call_args.kwargs["filters"]
    assert filters == {
        "tenant_id": "tenant-a",
        "owner_user_id": "user-a",
        "file_id": "file-a",
    }


def test_admin_search_is_limited_to_managed_users(vector_service, mock_vector_store):
    with bound_context(
        tenant_id="tenant-a",
        user_id="admin-a",
        role="admin",
        admin_id="admin-a",
    ):
        vector_service.search_chunks([0.1, 0.2, 0.3], filters={"owner_user_id": "user-a"})

    assert mock_vector_store.search_chunks.call_args.kwargs["filters"] == {
        "tenant_id": "tenant-a",
        "owner_admin_id": "admin-a",
    }


def test_user_chunk_write_uses_trusted_ownership(vector_service, mock_vector_store):
    with bound_context(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    ):
        vector_service.upsert_chunks([build_chunk(tenant_id="tenant-a", owner_user_id="forged")])

    chunk = mock_vector_store.upsert_chunks.call_args.args[0][0]
    assert chunk["tenant_id"] == "tenant-a"
    assert chunk["owner_user_id"] == "user-a"
    assert chunk["owner_admin_id"] == "admin-a"


def test_vector_scope_fails_closed_without_identity_in_production(vector_service, monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    with pytest.raises(AuthError, match="identity is missing"):
        vector_service.search_chunks([0.1, 0.2, 0.3])


def test_search_still_asks_the_store_for_a_ranked_search(vector_service, mock_vector_store):
    """Verification is additive: retrieval's own call is unchanged."""
    with bound_context(**ADMIN_A):
        vector_service.search_chunks([0.1, 0.2, 0.3], top_k=7)

    assert mock_vector_store.search_chunks.call_args.kwargs["top_k"] == 7
    mock_vector_store.lookup_ids.assert_not_called()
