"""What review state callers may read, and what stays internal."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock

from app.services.file_handlers import FileHandlers
from app.utils.common import utcnow
from app.tests._files_harness import (
    DummyProducer,
    make_actor,
    make_graph,
    make_repo,
    make_request,
    trigger_review,
)


def test_audit_trail_pagination_returns_cursor(config):
    repo = make_repo()
    file_doc = repo.get_by_id("file-1")
    for index in range(3):
        repo.insert_audit_event(
            {
                "event_id": f"event-{index}",
                "file_id": file_doc["file_id"],
                "document_id": file_doc["document_id"],
                "task_id": "task-1",
                "review_case_id": None,
                "decision_id": None,
                "event_type": f"event_{index}",
                "from_status": None,
                "to_status": None,
                "actor": make_actor(),
                "reason": "test",
                "details": {},
                "file_ref": {
                    "db": "files",
                    "collection": "files",
                    "file_id": file_doc["file_id"],
                    "document_id": file_doc["document_id"],
                    "filename": file_doc["filename"],
                },
                "created_at": utcnow() + timedelta(seconds=index),
            }
        )

    first_page, cursor = repo.get_audit_events("file-1", limit=2)
    second_page, next_cursor = repo.get_audit_events("file-1", limit=2, cursor=cursor)

    assert len(first_page) == 2
    assert cursor is not None
    assert len(second_page) == 1
    assert next_cursor is None


def test_rpc_get_and_list_still_expose_review_fields(config):
    repo = make_repo()
    repo.files["file-1"]["review_status"] = "pending"
    repo.files["file-1"]["latest_review_case_id"] = "review-123"
    producer = DummyProducer()
    handlers = FileHandlers(producer, repo, Mock(), config)

    get_reply = handlers.handle_get("corr-1", make_request("get", file_id="file-1"))
    list_reply = handlers.handle_list("corr-2", make_request("list"))

    assert get_reply["message_type"] == "reply"
    assert get_reply["success"] is True
    get_payload = get_reply["payload"]["file"]
    list_payload = list_reply["payload"]["files"][0]
    assert get_payload["review_status"] == "pending"
    assert get_payload["latest_review_case_id"] == "review-123"
    assert list_payload["review_status"] == "pending"
    assert list_payload["latest_review_case_id"] == "review-123"


def test_get_review_case_reply_exposes_extracted_text_hash(config):
    """The reviewer UI needs the hash to build a compliant decision payload."""

    repo = make_repo()
    graph = make_graph(repo, config)
    _, review_case = trigger_review(graph, repo)
    handlers = FileHandlers(DummyProducer(), repo, Mock(), config)

    reply = handlers.handle_get_review_case("corr-1", make_request("get_review_case", file_id="file-1"))

    assert reply["success"] is True
    assert reply["payload"]["extracted_text_hash"] == review_case["extracted_text_hash"]


def test_list_own_returns_sanitized_records_without_review_internals(config):
    """Uploaders may see their own files, but never review or pipeline internals."""

    repo = make_repo()
    repo.files["file-1"]["review_status"] = "pending"
    repo.files["file-1"]["latest_review_case_id"] = "review-123"
    repo.files["file-1"]["summary"] = "internal summary"
    handlers = FileHandlers(DummyProducer(), repo, Mock(), config)

    reply = handlers.handle_list_own("corr-1", make_request("list_own"))

    record = reply["payload"]["files"][0]
    assert record["file_id"] == "file-1"
    assert record["filename"] == "report.txt"
    assert record["status"] == "started"
    assert set(record) == {
        "file_id",
        "document_id",
        "filename",
        "content_type",
        "size",
        "status",
        "created_at",
        "updated_at",
    }
