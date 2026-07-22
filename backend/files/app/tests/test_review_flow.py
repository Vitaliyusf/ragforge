"""Tests for human-in-the-loop review and backward-compatible file flows."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.constants import FileAction
from app.core.errors import ValidationException
from app.services.file_handlers import FileHandlers
from app.services.file_ingestion_graph import FileIngestionGraph
from app.services.file_service import FileService
from app.utils.common import create_file_document, create_file_task_document, utcnow
from shared.context import bound_context


class DummyProducer:
    """Capture Kafka sends in memory."""

    def __init__(self):
        self.messages = []

    def send(self, topic, message):
        self.messages.append((topic, message))

    def flush(self):
        return None

    def is_connected(self):
        return True


@pytest.fixture(autouse=True)
def authenticated_request_context():
    """Give direct handler tests the identity normally verified at the RPC boundary."""
    with bound_context(
        user_id="test-admin",
        tenant_id="test-tenant",
        role="admin",
        admin_id="test-admin",
    ):
        yield


class FakeRepository:
    """In-memory repository used by graph and handler tests."""

    def __init__(self, file_doc=None, task_doc=None):
        self.files = {}
        self.tasks = {}
        self.review_cases = {}
        self.review_decisions = {}
        self.chunks = {}
        self.audit_events = []
        if file_doc:
            self.files[file_doc["file_id"]] = deepcopy(file_doc)
        if task_doc:
            self.tasks[task_doc["task_id"]] = deepcopy(task_doc)

    @contextmanager
    def transaction(self):
        yield None

    def create(self, file_doc, *, session=None):
        self.files[file_doc["file_id"]] = deepcopy(file_doc)
        return True

    def get_all(self):
        return [deepcopy(item) for item in self.files.values()]

    def get_by_id(self, file_id):
        doc = self.files.get(file_id)
        return deepcopy(doc) if doc else None

    def get_raw_by_id(self, file_id, *, session=None):
        doc = self.files.get(file_id)
        return deepcopy(doc) if doc else None

    def update_file(self, file_id, updates, *, session=None):
        if file_id not in self.files:
            return False
        self._deep_update(self.files[file_id], updates)
        self.files[file_id]["updated_at"] = utcnow()
        return True

    def update_stage(self, file_id, stage_name, status, *, session=None):
        return self.update_file(file_id, {f"stage.{stage_name}": status}, session=session)

    def update_status(self, file_id, status, *, session=None):
        return self.update_file(file_id, {"status": status}, session=session)

    def update_review_status(self, file_id, review_status, *, session=None):
        return self.update_file(file_id, {"review_status": review_status}, session=session)

    def update_summary(self, file_id, summary, *, session=None):
        return self.update_file(file_id, {"summary": summary, "stage.summary": "done"}, session=session)

    def update_metadata(self, file_id, keywords, *, session=None):
        return self.update_file(file_id, {"metadata.keywords": keywords, "stage.metadata": "done"}, session=session)

    def update_suggested_questions(self, file_id, questions, *, session=None):
        return self.update_file(file_id, {"suggested_questions": questions}, session=session)

    def get_suggested_questions_from_complete_files(self):
        return []

    def get_summary(self, file_id):
        doc = self.files.get(file_id)
        if not doc:
            return None
        return {"summary": doc.get("summary", ""), "stage": doc.get("stage", {}).get("summary", "waiting")}

    def delete(self, file_id, *, session=None):
        return self.files.pop(file_id, None) is not None

    def create_task(self, task_doc, *, session=None):
        self.tasks[task_doc["task_id"]] = deepcopy(task_doc)
        return True

    def get_task_by_id(self, task_id):
        doc = self.tasks.get(task_id)
        return deepcopy(doc) if doc else None

    def get_raw_task_by_id(self, task_id, *, session=None):
        return self.get_task_by_id(task_id)

    def get_latest_task_for_file(self, file_id):
        for task in self.tasks.values():
            if task["file_id"] == file_id:
                return deepcopy(task)
        return None

    def update_task(self, task_id, updates, *, session=None):
        if task_id not in self.tasks:
            return False
        self._deep_update(self.tasks[task_id], updates)
        self.tasks[task_id]["updated_at"] = utcnow()
        return True

    def create_review_case(self, review_case_doc, *, session=None):
        self.review_cases[review_case_doc["review_case_id"]] = deepcopy(review_case_doc)
        return True

    def get_review_case_by_id(self, review_case_id):
        doc = self.review_cases.get(review_case_id)
        return deepcopy(doc) if doc else None

    def get_raw_review_case_by_id(self, review_case_id, *, session=None):
        return self.get_review_case_by_id(review_case_id)

    def get_open_review_case_for_file(self, file_id):
        for review_case in self.review_cases.values():
            if review_case["file_id"] == file_id and review_case["status"] == "open":
                return deepcopy(review_case)
        return None

    def update_review_case(self, review_case_id, updates, *, session=None):
        if review_case_id not in self.review_cases:
            return False
        self._deep_update(self.review_cases[review_case_id], updates)
        return True

    def claim_review_case(
        self,
        review_case_id,
        *,
        extracted_text_hash,
        resume_token_hash,
        claim_id,
        claimed_at,
        session=None,
    ):
        review_case = self.review_cases.get(review_case_id)
        if not review_case:
            return False
        graph_interrupt = review_case.get("graph_interrupt", {})
        if (
            review_case.get("status") != "open"
            or review_case.get("decision_status") != "pending"
            or review_case.get("extracted_text_hash") != extracted_text_hash
            or graph_interrupt.get("resume_token_hash") != resume_token_hash
        ):
            return False
        self._deep_update(review_case, {
            "status": "resolving",
            "decision_status": "resolving",
            "resolution_claim_id": claim_id,
            "resolution_claimed_at": claimed_at,
        })
        return True

    def create_review_decision(self, decision_doc, *, session=None):
        self.review_decisions[decision_doc["decision_id"]] = deepcopy(decision_doc)
        return True

    def get_latest_review_decision(self, review_case_id):
        decisions = [
            decision
            for decision in self.review_decisions.values()
            if decision["review_case_id"] == review_case_id
        ]
        if not decisions:
            return None
        decisions.sort(key=lambda item: item["created_at"], reverse=True)
        return deepcopy(decisions[0])

    def create_chunks(self, chunk_docs, *, session=None):
        for chunk in chunk_docs:
            self.chunks[chunk["chunk_id"]] = deepcopy(chunk)
        return len(list(chunk_docs)) if not isinstance(chunk_docs, list) else len(chunk_docs)

    def delete_chunks_for_file(self, file_id, *, session=None):
        keys = [chunk_id for chunk_id, chunk in self.chunks.items() if chunk["file_id"] == file_id]
        for key in keys:
            del self.chunks[key]
        return len(keys)

    def get_next_chunk_version(self, document_id):
        versions = [chunk["chunk_version"] for chunk in self.chunks.values() if chunk["document_id"] == document_id]
        return (max(versions) + 1) if versions else 1

    def insert_audit_event(self, event_doc, *, session=None):
        self.audit_events.append(deepcopy(event_doc))
        self.audit_events.sort(key=lambda item: (item["created_at"], item["event_id"]), reverse=True)
        return True

    def get_audit_events(self, file_id, *, limit=50, cursor=None):
        filtered = [event for event in self.audit_events if event["file_id"] == file_id]
        if cursor:
            cursor_index = next((index for index, event in enumerate(filtered) if event["event_id"] == cursor), None)
            if cursor_index is not None:
                filtered = filtered[cursor_index + 1 :]
        page = filtered[:limit]
        next_cursor = page[-1]["event_id"] if len(page) == limit else None
        return deepcopy(page), next_cursor

    @staticmethod
    def _deep_update(document, updates):
        for key, value in updates.items():
            if "." not in key:
                document[key] = value
                continue
            target = document
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value


class StandaloneFallbackRepository(FakeRepository):
    """Repository double that simulates transaction fallback for standalone Mongo."""

    def __init__(self):
        super().__init__()
        self.transaction_calls = 0
        self.fallback_sessions = []

    @contextmanager
    def transaction(self):
        self.transaction_calls += 1
        self.fallback_sessions.append(None)
        yield None


@pytest.fixture
def config():
    return SimpleNamespace(
        service_name="files",
        langsmith_tracing_enabled=False,
        langsmith_api_key="",
        prompt_injection_threshold=0.8,
        pii_high_risk_threshold=0.8,
        unsafe_content_threshold=0.8,
        parser_problem_threshold=0.7,
        review_snippet_max_chars=64,
        chunk_preview_max_chars=24,
        chunk_size=16,
        chunk_overlap=4,
        review_resume_token_ttl_seconds=3600,
        files_events_topic="files.events",
        embedding_jobs_topic="embedding.jobs.requested",
        vector_db_delete_topic="vector_db.delete.requested",
        extract_topic="embedding.requests",
        response_topic="gateway.replies",
        upload_dir="uploads",
        max_upload_bytes=25 * 1024 * 1024,
    )


def make_repo():
    file_doc = create_file_document(
        "file-1",
        "report.txt",
        "uploads/test-tenant/file-1/report.txt",
        "text/plain",
        128,
        document_id="file-1",
    )
    task_doc = create_file_task_document("task-1", file_doc, graph_run_id="graph-1")
    file_doc["current_task_id"] = task_doc["task_id"]
    return FakeRepository(file_doc=file_doc, task_doc=task_doc)


def make_graph(repo, config):
    return FileIngestionGraph(repo, DummyProducer(), Mock(), config)


def make_actor():
    return {"actor_id": "user-1", "actor_type": "human", "display_name": "Reviewer"}


def outbound_payload(message):
    return message["payload"]


def make_request(action, **payload):
    return {
        "message_id": "msg-1",
        "message_type": "query",
        "action": action,
        "source_service": "gateway",
        "target_service": "files",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "reply_to": "gateway.replies",
        "payload": payload,
    }


def trigger_review(graph, repo):
    outbound = graph.handle_extraction_completion(
        file_doc=repo.get_by_id("file-1"),
        task_doc=repo.get_task_by_id("task-1"),
        extracted_text="Employee SSN 123-45-6789 appears in this report.",
        diagnostics={"parser": "txt", "warnings": []},
        actor=make_actor(),
    )
    review_case = repo.get_open_review_case_for_file("file-1")
    return outbound, review_case


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


def test_issue_detection_creates_review_case_with_bounded_snippet(config):
    repo = make_repo()
    graph = make_graph(repo, config)

    outbound, review_case = trigger_review(graph, repo)

    assert repo.files["file-1"]["status"] == "awaiting_review"
    assert repo.files["file-1"]["review_status"] == "pending"
    assert review_case is not None
    assert review_case["extracted_text_hash"]
    assert len(review_case["problematic_text"]) <= config.review_snippet_max_chars
    assert review_case["allowed_actions"] == ["delete_file", "remove_problematic_text", "accept_as_is"]
    assert outbound[0].message["message_type"] == "event"
    assert outbound_payload(outbound[0].message)["event_type"] == "files.review.required"


def test_delete_file_decision_rejects_file_and_requests_cleanup_when_needed(config):
    repo = make_repo()
    graph = make_graph(repo, config)
    _, review_case = trigger_review(graph, repo)
    repo.chunks["existing"] = {
        "chunk_id": "existing",
        "file_id": "file-1",
        "document_id": "file-1",
        "chunk_version": 1,
    }
    repo.files["file-1"]["stage"]["chunking"] = "done"

    outbound = graph.handle_review_decision(
        file_doc=repo.get_by_id("file-1"),
        review_case_doc=review_case,
        task_doc=repo.get_task_by_id("task-1"),
        decision_payload={
            "file_id": "file-1",
            "review_case_id": review_case["review_case_id"],
            "decision": "delete_file",
            "based_on_text_hash": review_case["extracted_text_hash"],
            "patch_map": [],
        },
        actor=make_actor(),
    )

    assert repo.files["file-1"]["status"] == "rejected"
    assert repo.files["file-1"]["review_status"] == "rejected"
    assert repo.tasks["task-1"]["status"] == "rejected"
    assert any(outbound_payload(message.message)["event_type"] == "vector_db.delete.requested" for message in outbound)


def test_remove_problematic_text_decision_creates_sanitized_chunks(config):
    repo = make_repo()
    graph = make_graph(repo, config)
    _, review_case = trigger_review(graph, repo)

    outbound = graph.handle_review_decision(
        file_doc=repo.get_by_id("file-1"),
        review_case_doc=review_case,
        task_doc=repo.get_task_by_id("task-1"),
        decision_payload={
            "file_id": "file-1",
            "review_case_id": review_case["review_case_id"],
            "decision": "remove_problematic_text",
            "based_on_text_hash": review_case["extracted_text_hash"],
            "patch_map": review_case["redaction_patch_map"],
        },
        actor=make_actor(),
    )

    assert repo.files["file-1"]["review_status"] == "approved_sanitized"
    assert repo.files["file-1"]["sanitized_text_version"] == 1
    assert repo.chunks
    assert all(chunk["review_status"] == "sanitized" for chunk in repo.chunks.values())
    assert all(chunk["text_source"] == "sanitized" for chunk in repo.chunks.values())
    assert any(message.message["action"] == "process_embedding_job" for message in outbound)


def test_accept_as_is_decision_marks_chunks_with_risk(config):
    repo = make_repo()
    graph = make_graph(repo, config)
    _, review_case = trigger_review(graph, repo)

    graph.handle_review_decision(
        file_doc=repo.get_by_id("file-1"),
        review_case_doc=review_case,
        task_doc=repo.get_task_by_id("task-1"),
        decision_payload={
            "file_id": "file-1",
            "review_case_id": review_case["review_case_id"],
            "decision": "accept_as_is",
            "based_on_text_hash": review_case["extracted_text_hash"],
            "patch_map": [],
        },
        actor=make_actor(),
    )

    assert repo.files["file-1"]["review_status"] == "approved_as_is"
    assert repo.files["file-1"]["accepted_risk_categories"] == ["pii_high_risk"]
    assert all(chunk["review_status"] == "accepted_with_risk" for chunk in repo.chunks.values())


def test_duplicate_decision_is_rejected(config):
    repo = make_repo()
    graph = make_graph(repo, config)
    _, review_case = trigger_review(graph, repo)
    repo.review_cases[review_case["review_case_id"]]["status"] = "resolved"
    repo.review_cases[review_case["review_case_id"]]["decision_status"] = "accept_as_is"

    with pytest.raises(ValidationException):
        graph.handle_review_decision(
            file_doc=repo.get_by_id("file-1"),
            review_case_doc=review_case,
            task_doc=repo.get_task_by_id("task-1"),
            decision_payload={
                "file_id": "file-1",
                "review_case_id": review_case["review_case_id"],
                "decision": "accept_as_is",
                "based_on_text_hash": review_case["extracted_text_hash"],
                "patch_map": [],
            },
            actor=make_actor(),
        )


def test_review_decision_fails_closed_when_atomic_claim_is_lost(config):
    repo = make_repo()
    graph = make_graph(repo, config)
    _, review_case = trigger_review(graph, repo)
    repo.claim_review_case = lambda *args, **kwargs: False

    with pytest.raises(ValidationException, match="already being resolved"):
        graph.handle_review_decision(
            file_doc=repo.get_by_id("file-1"),
            review_case_doc=review_case,
            task_doc=repo.get_task_by_id("task-1"),
            decision_payload={
                "file_id": "file-1",
                "review_case_id": review_case["review_case_id"],
                "decision": "accept_as_is",
                "based_on_text_hash": review_case["extracted_text_hash"],
                "patch_map": [],
            },
            actor=make_actor(),
        )

    assert repo.review_decisions == {}
    assert repo.chunks == {}


def test_invalid_patch_map_is_rejected(config):
    repo = make_repo()
    graph = make_graph(repo, config)
    _, review_case = trigger_review(graph, repo)

    with pytest.raises(ValidationException):
        graph.handle_review_decision(
            file_doc=repo.get_by_id("file-1"),
            review_case_doc=review_case,
            task_doc=repo.get_task_by_id("task-1"),
            decision_payload={
                "file_id": "file-1",
                "review_case_id": review_case["review_case_id"],
                "decision": "remove_problematic_text",
                "based_on_text_hash": review_case["extracted_text_hash"],
                "patch_map": [],
            },
            actor=make_actor(),
        )


def test_extracted_text_hash_mismatch_is_rejected(config):
    repo = make_repo()
    graph = make_graph(repo, config)
    _, review_case = trigger_review(graph, repo)

    with pytest.raises(ValidationException):
        graph.handle_review_decision(
            file_doc=repo.get_by_id("file-1"),
            review_case_doc=review_case,
            task_doc=repo.get_task_by_id("task-1"),
            decision_payload={
                "file_id": "file-1",
                "review_case_id": review_case["review_case_id"],
                "decision": "accept_as_is",
                "based_on_text_hash": "wrong-hash",
                "patch_map": [],
            },
            actor=make_actor(),
        )


def test_expired_resume_token_is_rejected(config):
    repo = make_repo()
    graph = make_graph(repo, config)
    _, review_case = trigger_review(graph, repo)
    repo.review_cases[review_case["review_case_id"]]["graph_interrupt"]["resume_token_expires_at"] = utcnow() - timedelta(seconds=1)

    with pytest.raises(ValidationException):
        graph.handle_review_decision(
            file_doc=repo.get_by_id("file-1"),
            review_case_doc=review_case,
            task_doc=repo.get_task_by_id("task-1"),
            decision_payload={
                "file_id": "file-1",
                "review_case_id": review_case["review_case_id"],
                "decision": "accept_as_is",
                "based_on_text_hash": review_case["extracted_text_hash"],
                "patch_map": [],
            },
            actor=make_actor(),
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
    assert command_message["message_type"] == "command"
    assert command_message["action"] == "extract"
    assert command_message["source_service"] == "files"
    assert command_message["target_service"] == "embedding"
    assert command_message["payload"]["path"].endswith("file-2/report.txt")
    assert reply_message["message_type"] == "reply"
    assert reply_message["success"] is True


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


def test_list_own_is_allowed_for_non_admin_roles():
    """The uploader-scoped listing must not be gated behind the admin check."""

    with bound_context(user_id="user-1", tenant_id="tenant-a", role="user", admin_id="admin-a"):
        FileService._authorize_action(FileAction.LIST_OWN)
        with pytest.raises(ValidationException):
            FileService._authorize_action(FileAction.LIST)
