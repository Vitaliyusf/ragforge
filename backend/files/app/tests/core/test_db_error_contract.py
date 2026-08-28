"""Regression coverage for files database errors and transaction fallback."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import DatabaseException, ErrorCode
from app.db import session as db_session
from app.db.repository import FileRepository
from shared.context import bound_context


class ExplodingCollection:
    """Collection double that raises on write operations."""

    def insert_one(self, *_args, **_kwargs):
        raise RuntimeError("boom")


class MinimalCollection:
    """Collection double that supplies the repository client shape."""

    def __init__(self, client=None):
        self.database = SimpleNamespace(client=client)


class RecordingLogger:
    """Capture repository warnings without requiring the shared logger."""

    def __init__(self):
        self.entries = []

    def log(self, location, message, data=None, hypothesis_id="A", **_kwargs):
        self.entries.append(
            {
                "location": location,
                "message": message,
                "data": data or {},
                "hypothesis_id": hypothesis_id,
            }
        )


class SupportedTransaction:
    """Transaction context that succeeds."""

    def __init__(self, client):
        self.client = client

    def __enter__(self):
        self.client.transaction_enters += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.client.transaction_exits += 1
        return False


class SupportedSession:
    """Session double that supports transactions."""

    def __init__(self, client):
        self.client = client

    def __enter__(self):
        self.client.session_enters += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.client.session_exits += 1
        return False

    def start_transaction(self):
        return SupportedTransaction(self.client)


class SupportedClient:
    """Client double whose topology supports transactions."""

    def __init__(self):
        self.start_session_calls = 0
        self.session_enters = 0
        self.session_exits = 0
        self.transaction_enters = 0
        self.transaction_exits = 0
        self.admin = SimpleNamespace(command=self.command)

    def command(self, name):
        assert name in {"hello", "isMaster"}
        return {"setName": "rs0"}

    def start_session(self):
        self.start_session_calls += 1
        return SupportedSession(self)


class StandaloneClient:
    """Client double for a standalone Mongo topology."""

    def __init__(self):
        self.start_session_calls = 0
        self.command_calls = []
        self.admin = SimpleNamespace(command=self.command)

    def command(self, name):
        self.command_calls.append(name)
        assert name in {"hello", "isMaster"}
        return {"ok": 1.0}

    def start_session(self):
        self.start_session_calls += 1
        raise AssertionError("standalone fallback should avoid opening a session")


class FailingTransaction:
    """Transaction context that raises the standalone Mongo transaction error."""

    def __enter__(self):
        raise RuntimeError(
            "Transaction numbers are only allowed on a replica set member or mongos"
        )

    def __exit__(self, exc_type, exc, tb):
        return False


class FailingSession:
    """Session double whose transaction open fails with the standalone error."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def start_transaction(self):
        return FailingTransaction()


class FailingTransactionClient:
    """Client double that claims transaction support but fails when opening one."""

    def __init__(self):
        self.start_session_calls = 0
        self.admin = SimpleNamespace(command=self.command)

    def command(self, name):
        assert name in {"hello", "isMaster"}
        return {"setName": "rs0"}

    def start_session(self):
        self.start_session_calls += 1
        return FailingSession()


def test_repository_create_wraps_database_errors_with_shared_constructor():
    repo = FileRepository(MinimalCollection())
    repo.collection = ExplodingCollection()

    with bound_context(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    ):
        with pytest.raises(DatabaseException) as exc_info:
            repo.create({"file_id": "file-1"})

    assert exc_info.value.error_code == ErrorCode.DATABASE_ERROR
    assert exc_info.value.message == "Failed to create file: boom"


def test_get_client_uses_keyword_error_code_for_connection_failures(monkeypatch):
    db_session._client = None
    monkeypatch.setattr(
        db_session,
        "settings",
        SimpleNamespace(mongodb_max_retries=1, mongodb_retry_delay=0, mongodb_url="mongodb://bad"),
    )

    class FailingMongoClient:
        def __init__(self, *_args, **_kwargs):
            pass

        @property
        def admin(self):
            return self

        def command(self, *_args, **_kwargs):
            raise RuntimeError("connect failed")

    monkeypatch.setattr(db_session, "MongoClient", FailingMongoClient)

    with pytest.raises(DatabaseException) as exc_info:
        db_session.get_client()

    assert exc_info.value.error_code == ErrorCode.DATABASE_CONNECTION_ERROR
    assert exc_info.value.message == "Failed to connect to MongoDB after 1 attempts: connect failed"


def test_transaction_uses_session_when_transactions_supported():
    client = SupportedClient()
    repo = FileRepository(MinimalCollection(client), client=client)
    caller_body_calls = 0

    with repo.transaction() as session:
        caller_body_calls += 1
        assert session is not None

    assert caller_body_calls == 1
    assert client.start_session_calls == 1
    assert client.session_enters == 1
    assert client.session_exits == 1
    assert client.transaction_enters == 1
    assert client.transaction_exits == 1
    assert repo._transactions_supported is True


def test_transaction_falls_back_to_none_for_standalone_topology():
    client = StandaloneClient()
    logger = RecordingLogger()
    repo = FileRepository(MinimalCollection(client), client=client, logger=logger)
    caller_body_calls = 0

    with repo.transaction() as session:
        caller_body_calls += 1
        assert session is None

    assert caller_body_calls == 1
    assert client.start_session_calls == 0
    assert repo._transactions_supported is False
    assert logger.entries[0]["location"] == "db:transaction"
    assert logger.entries[0]["data"]["reason"] == "standalone_mongo_topology"


def test_transaction_capability_is_cached_after_standalone_detection():
    client = StandaloneClient()
    logger = RecordingLogger()
    repo = FileRepository(MinimalCollection(client), client=client, logger=logger)

    with repo.transaction() as session:
        assert session is None
    with repo.transaction() as session:
        assert session is None

    assert client.command_calls == ["hello"]
    assert client.start_session_calls == 0
    assert len(logger.entries) == 1


def test_unsupported_transaction_open_selects_fallback_before_caller_body():
    client = FailingTransactionClient()
    logger = RecordingLogger()
    repo = FileRepository(MinimalCollection(client), client=client, logger=logger)
    caller_body_calls = 0

    with repo.transaction() as session:
        caller_body_calls += 1
        assert session is None

    assert caller_body_calls == 1
    assert client.start_session_calls == 1
    assert repo._transactions_supported is False
    assert len(logger.entries) == 1
    assert "replica set member or mongos" in logger.entries[0]["data"]["reason"]


def test_database_failure_after_caller_body_starts_is_not_replayed():
    client = SupportedClient()
    logger = RecordingLogger()
    repo = FileRepository(MinimalCollection(client), client=client, logger=logger)
    caller_body_calls = 0

    with pytest.raises(RuntimeError, match="database write failed"):
        with repo.transaction():
            caller_body_calls += 1
            raise RuntimeError("database write failed")

    assert caller_body_calls == 1
    assert repo._transactions_supported is True
    assert logger.entries == []


def test_unsupported_error_after_caller_body_starts_is_not_fallback_or_replay():
    client = SupportedClient()
    logger = RecordingLogger()
    repo = FileRepository(MinimalCollection(client), client=client, logger=logger)
    caller_body_calls = 0
    message = "Transaction numbers are only allowed on a replica set member or mongos"

    with pytest.raises(RuntimeError, match="replica set member or mongos"):
        with repo.transaction():
            caller_body_calls += 1
            raise RuntimeError(message)

    assert caller_body_calls == 1
    assert repo._transactions_supported is True
    assert logger.entries == []
