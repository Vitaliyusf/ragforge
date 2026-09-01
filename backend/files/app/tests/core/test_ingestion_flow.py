"""End-to-end ingestion for files that need no human review."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.services.file_handlers import FileHandlers
from app.core.constants import IngestionState
from app.tests._files_harness import (
    authenticated_request_context,  # noqa: F401  (autouse within this module)
    DummyProducer,
    FakeRepository,
    StandaloneFallbackRepository,
    make_actor,
    make_graph,
    make_repo,
    make_request,
    outbound_payload,
)


def test_clean_file_flow_creates_clean_chunks(config):
    repo = make_repo()
    graph = make_graph(repo, config)

    outbound = graph.handle_extraction_completion(
        file_doc=repo.get_by_id("file-1"),
        task_doc=repo.get_task_by_id("task-1"),
        extracted_text="This is a harmless project update with no sensitive text.",
        diagnostics={"parser": "txt", "warnings": []},
        actor=make_actor(),
    )

    assert repo.files["file-1"]["review_status"] == "not_required"
    assert repo.files["file-1"]["stage"]["chunking"] == "done"
    assert repo.tasks["task-1"]["status"] == "completed"
    assert repo.tasks["task-1"]["current_node"] == IngestionState.FINALIZE.value
    assert repo.review_cases == {}
    assert repo.chunks
    assert all(chunk["review_status"] == "clean" for chunk in repo.chunks.values())
    assert all(chunk["retrieval_allowed"] is True for chunk in repo.chunks.values())
    assert all(chunk["source_name"] == "report.txt" for chunk in repo.chunks.values())
    assert all("page" in chunk and "section" in chunk for chunk in repo.chunks.values())
    assert outbound[0].message["action"] == "files.chunking.completed"
    assert outbound_payload(outbound[0].message)["event_type"] == "files.chunking.completed"
    assert outbound[1].message["message_type"] == "command"
    assert outbound[1].message["action"] == "process_embedding_job"
    assert outbound_payload(outbound[1].message)["job_id"]


@pytest.mark.parametrize(
    ("waiting_stage", "handler_name", "payload"),
    [
        ("summary", "handle_update_summary", {"summary": "Completed summary"}),
        ("metadata", "handle_update_metadata", {"keywords": ["rabbitmq", "kafka"]}),
    ],
)
def test_final_content_update_marks_file_complete(config, waiting_stage, handler_name, payload):
    repo = make_repo()
    handlers = FileHandlers(DummyProducer(), repo, Mock(), config)
    repo.files["file-1"]["status"] = "processing"
    for stage in repo.files["file-1"]["stage"]:
        repo.files["file-1"]["stage"][stage] = "done"
    repo.files["file-1"]["stage"][waiting_stage] = "waiting"

    getattr(handlers, handler_name)({"payload": {"file_id": "file-1", **payload}})

    assert repo.files["file-1"]["stage"][waiting_stage] == "done"
    assert repo.files["file-1"]["status"] == "complete"


def test_clean_flow_publishes_typed_embedding_job_command(config):
    """Chunking completion should hand off to embedding with the typed command envelope."""

    repo = make_repo()
    graph = make_graph(repo, config)

    outbound = graph.handle_extraction_completion(
        file_doc=repo.get_by_id("file-1"),
        task_doc=repo.get_task_by_id("task-1"),
        extracted_text="This is a harmless project update with no sensitive text.",
        diagnostics={"parser": "txt", "warnings": []},
        actor=make_actor(),
    )

    job_message = outbound[1].message
    assert job_message["message_type"] == "command"
    assert job_message["action"] == "process_embedding_job"
    assert job_message["source_service"] == "files"
    assert job_message["target_service"] == "embedding"
    assert job_message["payload"]["job_id"]
    assert job_message["payload"]["requested_at"]
    assert len(job_message["payload"]["chunks"]) >= 1


def test_start_file_ingestion_publishes_enveloped_extract_command(config):
    repo = FakeRepository()
    producer = DummyProducer()
    handlers = FileHandlers(producer, repo, Mock(), config)

    reply_message = handlers.handle_start_file_ingestion(
        "corr-1",
        make_request(
            "start_file_ingestion",
            file_id="file-2",
            document_id="file-2",
            filename="report.txt",
            content_type="text/plain",
            content="ZmFrZQ==",
        ),
    )

    command_topic, command_message = producer.messages[0]
    assert command_topic == "embedding.requests"
    assert producer.keys[0] == "file-2"
    assert command_message["message_type"] == "command"
    assert command_message["action"] == "extract"
    assert command_message["source_service"] == "files"
    assert command_message["target_service"] == "embedding"
    # Normalize separators: the path is built with os.path.join, so it is
    # backslash-delimited when the suite runs on Windows.
    assert command_message["payload"]["path"].replace("\\", "/").endswith("file-2/report.txt")
    assert reply_message["message_type"] == "reply"
    assert reply_message["success"] is True


def test_start_file_ingestion_accepts_base64_content_over_rabbitmq(config):
    repo = FakeRepository()
    producer = DummyProducer()
    handlers = FileHandlers(producer, repo, Mock(), config)

    reply = handlers.handle_start_file_ingestion(
        "corr-1",
        make_request(
            "start_file_ingestion",
            file_id="file-2",
            filename="report.txt",
            content_type="text/plain",
            content="ZmFrZQ==",
        ),
    )

    assert reply["success"] is True
    assert repo.files["file-2"]["size"] == 4
    assert producer.messages[0][1]["action"] == "extract"


def test_start_file_ingestion_succeeds_with_standalone_transaction_fallback(config):
    repo = StandaloneFallbackRepository()
    producer = DummyProducer()
    handlers = FileHandlers(producer, repo, Mock(), config)

    reply_message = handlers.handle_start_file_ingestion(
        "corr-1",
        make_request(
            "start_file_ingestion",
            file_id="file-2",
            document_id="file-2",
            filename="report.txt",
            content_type="text/plain",
            content="ZmFrZQ==",
        ),
    )

    assert repo.transaction_calls == 1
    assert repo.fallback_sessions == [None]
    assert repo.files["file-2"]["current_task_id"] is not None
    assert len(repo.audit_events) == 1
    assert producer.messages[0][1]["action"] == "extract"
    assert reply_message["success"] is True
