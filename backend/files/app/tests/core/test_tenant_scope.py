"""Fail-closed tenant and owner scoping tests for file persistence."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import DatabaseException
from app.db._base import BaseRepository
from app.db._chunks import ChunksRepositoryMixin
from app.db._files import FilesRepositoryMixin
from app.utils.common import validate_managed_file_path
from shared.context import bound_context


class FakeCollection:
    database = SimpleNamespace(client=None)


class RecordingCollection(FakeCollection):
    def __init__(self):
        self.query = None
        self.projection = None

    def find(self, query, projection):
        self.query = query
        self.projection = projection
        return []


class ScopedFilesRepository(FilesRepositoryMixin, BaseRepository):
    pass


class ScopedChunksRepository(ChunksRepositoryMixin, BaseRepository):
    pass


def _repository() -> BaseRepository:
    return BaseRepository(FakeCollection())


@pytest.mark.parametrize(
    ("identity", "expected_boundary"),
    [
        (
            {"tenant_id": "tenant-a", "user_id": "user-a", "role": "user", "admin_id": "admin-a"},
            {"tenant_id": "tenant-a", "owner_user_id": "user-a"},
        ),
        (
            {"tenant_id": "tenant-a", "user_id": "admin-a", "role": "admin", "admin_id": "admin-a"},
            {"tenant_id": "tenant-a", "owner_admin_id": "admin-a"},
        ),
        (
            {"tenant_id": "tenant-a", "user_id": "files-service", "role": "service"},
            {"tenant_id": "tenant-a"},
        ),
    ],
)
def test_scope_filter_enforces_role_boundary(identity, expected_boundary) -> None:
    with bound_context(**identity):
        query = _repository()._scope_filter({"file_id": "file-a"})

    assert query == {"$and": [expected_boundary, {"file_id": "file-a"}]}


def test_scope_document_stamps_owner_from_trusted_context() -> None:
    with bound_context(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    ):
        document = _repository()._scope_document({"file_id": "file-a"})

    assert document["tenant_id"] == "tenant-a"
    assert document["owner_user_id"] == "user-a"
    assert document["owner_admin_id"] == "admin-a"


def test_cross_tenant_document_write_is_rejected() -> None:
    with bound_context(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    ):
        with pytest.raises(DatabaseException, match="Cross-tenant"):
            _repository()._scope_document({"file_id": "file-a", "tenant_id": "tenant-b"})


def test_filename_lookup_is_tenant_scoped_for_an_authorized_admin() -> None:
    collection = RecordingCollection()
    repository = ScopedFilesRepository(collection)

    with bound_context(
        tenant_id="tenant-a",
        user_id="admin-a",
        role="admin",
        admin_id="admin-a",
    ):
        assert repository.get_filename_records() == []

    assert collection.query == {"tenant_id": "tenant-a"}
    assert collection.projection == {"_id": 0, "file_id": 1, "filename": 1}


def test_eval_file_readiness_lookup_is_tenant_scoped() -> None:
    collection = RecordingCollection()
    repository = ScopedFilesRepository(collection)

    with bound_context(
        tenant_id="tenant-a", user_id="admin-a", role="admin", admin_id="admin-a"
    ):
        assert repository.get_eval_file_records(["file-a"]) == []

    assert collection.query == {
        "$and": [{"tenant_id": "tenant-a"}, {"file_id": {"$in": ["file-a"]}}]
    }


def test_eval_chunk_lookup_is_tenant_scoped_without_owner_narrowing() -> None:
    primary = FakeCollection()
    chunks = RecordingCollection()
    repository = ScopedChunksRepository(primary)
    repository.file_chunks_collection = chunks

    with bound_context(
        tenant_id="tenant-a", user_id="admin-a", role="admin", admin_id="admin-a"
    ):
        assert repository.get_eval_chunk_records(["file-a"]) == []

    assert chunks.query == {
        "$and": [{"tenant_id": "tenant-a"}, {"file_id": {"$in": ["file-a"]}}]
    }


def test_user_cannot_forge_document_owner() -> None:
    with bound_context(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    ):
        document = _repository()._scope_document({
            "file_id": "file-a",
            "owner_user_id": "victim-user",
            "owner_admin_id": "victim-admin",
        })

    assert document["owner_user_id"] == "user-a"
    assert document["owner_admin_id"] == "admin-a"


def test_admin_cannot_write_into_another_admin_scope() -> None:
    with bound_context(
        tenant_id="tenant-a",
        user_id="admin-a",
        role="admin",
        admin_id="admin-a",
    ):
        with pytest.raises(DatabaseException, match="administrator scope"):
            _repository()._scope_document({"file_id": "file-a", "owner_admin_id": "admin-b"})


def test_missing_identity_fails_closed_when_internal_auth_is_required(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    with pytest.raises(Exception, match="identity is missing"):
        _repository()._scope_filter({"file_id": "file-a"})


def test_managed_file_path_cannot_escape_tenant_directory(tmp_path) -> None:
    valid = tmp_path / "tenant-a" / "file-a" / "report.txt"
    assert validate_managed_file_path(str(tmp_path), "tenant-a", "file-a", str(valid)) == valid.resolve()

    with pytest.raises(ValueError, match="outside"):
        validate_managed_file_path(
            str(tmp_path),
            "tenant-a",
            "file-a",
            str(tmp_path / "tenant-b" / "file-a" / "report.txt"),
        )
