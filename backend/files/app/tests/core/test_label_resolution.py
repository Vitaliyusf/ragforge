"""Resolving human-supplied file and chunk labels to stored records."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.constants import FileAction
from shared.errors import ValidationError as ValidationException
from app.services.file_handlers import FileHandlers
from app.services.file_service import FileService
from shared.context import bound_context
from app.tests._files_harness import (
    authenticated_request_context,  # noqa: F401  (autouse within this module)
    DummyProducer,
    FakeRepository,
    make_request,
)


def test_chunk_label_resolution_is_admin_only():
    with bound_context(user_id="user-1", tenant_id="tenant-a", role="user", admin_id="admin-a"):
        with pytest.raises(ValidationException):
            FileService._authorize_action(FileAction.RESOLVE_CHUNK_LABELS)


def test_file_label_resolution_prefers_exact_and_never_selects_ambiguous(config):
    repo = FakeRepository()
    repo.files = {
        "file-1": {"file_id": "file-1", "filename": "Report.pdf"},
        "file-2": {"file_id": "file-2", "filename": "report.pdf"},
    }
    handlers = FileHandlers(DummyProducer(), repo, Mock(), config)

    reply = handlers.handle_resolve_file_labels(
        "corr-1",
        make_request(
            "resolve_file_labels",
            labels=["Report.pdf", "REPORT.PDF", "missing.pdf"],
        ),
    )

    exact, normalized, missing = reply["payload"]["resolutions"]
    assert exact == {
        "label": "Report.pdf",
        "status": "RESOLVED",
        "file_id": "file-1",
        "candidate_file_ids": [],
    }
    assert normalized["status"] == "AMBIGUOUS_FILE_MATCH"
    assert normalized["file_id"] is None
    assert normalized["candidate_file_ids"] == ["file-1", "file-2"]
    assert missing["status"] == "UNRESOLVED_FILE"


def test_chunk_label_resolution_is_literal_whitespace_normalized_and_multi_match(config):
    repo = FakeRepository()
    repo.files["file-1"] = {
        "file_id": "file-1",
        "filename": "Guide.pdf",
        "status": "complete",
        "review_status": "clean",
    }
    repo.chunks = {
        "c1": {
            "chunk_id": "c1",
            "file_id": "file-1",
            "chunk_version": 2,
            "text": "Refunds are available\nfor 30 days.",
            "retrieval_allowed": True,
            "review_status": "clean",
        },
        "c2": {
            "chunk_id": "c2",
            "file_id": "file-1",
            "chunk_version": 2,
            "text": "Summary: Refunds are available for 30 days. Keep the receipt.",
            "retrieval_allowed": True,
            "review_status": "clean",
        },
        "c3": {
            "chunk_id": "c3",
            "file_id": "file-1",
            "chunk_version": 2,
            "text": "refunds are available for 30 days.",
            "retrieval_allowed": True,
            "review_status": "clean",
        },
        "old": {
            "chunk_id": "old",
            "file_id": "file-1",
            "chunk_version": 1,
            "text": "Refunds are available for 30 days.",
            "retrieval_allowed": True,
            "review_status": "clean",
        },
    }
    handlers = FileHandlers(DummyProducer(), repo, Mock(), config)

    reply = handlers.handle_resolve_chunk_labels(
        "corr-1",
        make_request(
            "resolve_chunk_labels",
            items=[
                {
                    "item_id": "q1",
                    "file_ids": ["file-1"],
                    "facts": ["Refunds  are available for 30 days."],
                }
            ],
        ),
    )

    resolution = reply["payload"]["resolutions"][0]
    assert resolution["files"] == [
        {"file_id": "file-1", "status": "READY", "searchable": True}
    ]
    assert resolution["facts"][0]["chunk_ids"] == ["c1", "c2"]
    assert resolution["chunk_ids"] == ["c1", "c2"]
    assert "text" not in resolution


def test_chunk_label_resolution_reports_unready_files_and_unresolved_facts(config):
    repo = FakeRepository()
    repo.files["processing"] = {
        "file_id": "processing",
        "filename": "Pending.pdf",
        "status": "processing",
        "review_status": "clean",
    }
    repo.files["deleted"] = {
        "file_id": "deleted",
        "filename": "Deleted.pdf",
        "status": "rejected",
        "review_status": "removed",
    }
    handlers = FileHandlers(DummyProducer(), repo, Mock(), config)

    reply = handlers.handle_resolve_chunk_labels(
        "corr-1",
        make_request(
            "resolve_chunk_labels",
            items=[
                {
                    "item_id": "q1",
                    "file_ids": ["missing", "processing", "deleted"],
                    "facts": ["A deterministic fact."],
                }
            ],
        ),
    )

    resolution = reply["payload"]["resolutions"][0]
    assert [entry["status"] for entry in resolution["files"]] == [
        "FILE_MISSING",
        "FILE_NOT_SEARCHABLE",
        "FILE_DELETED",
    ]
    assert resolution["facts"] == [
        {"fact": "A deterministic fact.", "status": "UNRESOLVED_FACT", "chunk_ids": []}
    ]
