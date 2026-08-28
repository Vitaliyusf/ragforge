"""Typed RPC replies and role checks at the file service boundary."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.constants import FileAction
from app.core.errors import ValidationException
from app.services.file_handlers import FileHandlers
from app.services.file_service import FileService
from shared.context import bound_context
from app.tests._files_harness import (
    authenticated_request_context,  # noqa: F401  (autouse within this module)
    DummyProducer,
    make_repo,
    make_request,
)


def test_send_error_uses_shared_validation_payload(config):
    repo = make_repo()
    producer = DummyProducer()
    handlers = FileHandlers(producer, repo, Mock(), config)

    message = handlers._send_error(  # noqa: SLF001 - targeted regression for shared error serialization
        "corr-1",
        "file_id is required",
        request=make_request("get"),
        reply_topic="gateway.replies",
    )

    assert message["message_type"] == "reply"
    assert message["success"] is False
    assert message["correlation_id"] == "corr-1"
    assert message["error"]["code"] == "VALIDATION_ERROR"
    assert message["error"]["message"] == "file_id is required"


def test_file_service_unknown_action_returns_typed_error_reply(config):
    repo = make_repo()
    producer = DummyProducer()
    service = FileService(producer, repo, Mock(), config)

    result = service.process_request(make_request("unknown_action"))

    assert result["message_type"] == "reply"
    assert result["success"] is False
    assert result["action"] == "unknown_action"
    assert result["correlation_id"] == "corr-1"
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert result["error"]["message"] == "Unknown action: unknown_action"


def test_list_own_is_allowed_for_non_admin_roles():
    """The uploader-scoped listing must not be gated behind the admin check."""

    with bound_context(user_id="user-1", tenant_id="tenant-a", role="user", admin_id="admin-a"):
        FileService._authorize_action(FileAction.LIST_OWN)
        with pytest.raises(ValidationException):
            FileService._authorize_action(FileAction.LIST)
