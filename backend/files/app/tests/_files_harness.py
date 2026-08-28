"""Shared fakes and builders for `files` ingestion and review tests.

Cross-domain on purpose: ingestion, review-decision and RPC-contract tests
all drive the real graph, handlers and service against these doubles.
Fixtures are re-exported by each lane's conftest.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.file_ingestion_state_machine import FileIngestionStateMachine
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
def authenticated_request_context(monkeypatch):
    """Give direct handler tests the identity normally verified at the RPC boundary.

    ``INTERNAL_AUTH_REQUIRED`` is cleared explicitly: these tests call handlers
    directly rather than through the signed RPC envelope, and leaving the
    variable ambient makes results depend on the shell. Inside a service
    container it is set to "true", which turns unrelated assertions into
    "signed authentication context is required" failures. Tests that do want
    the check enabled set it themselves (see test_tenant_scope.py).
    """
    monkeypatch.delenv("INTERNAL_AUTH_REQUIRED", raising=False)
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

    def get_filename_records(self):
        return [
            {"file_id": item["file_id"], "filename": item["filename"]}
            for item in self.files.values()
        ]

    def get_eval_file_records(self, file_ids):
        return [
            {
                "file_id": file_id,
                "status": self.files[file_id].get("status"),
                "review_status": self.files[file_id].get("review_status"),
            }
            for file_id in file_ids
            if file_id in self.files
        ]

    def get_eval_chunk_records(self, file_ids):
        return [
            deepcopy(chunk)
            for chunk in self.chunks.values()
            if chunk.get("file_id") in file_ids
        ]

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
    return FileIngestionStateMachine(repo, DummyProducer(), Mock(), config)


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
