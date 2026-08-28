"""What each reviewer decision does to the file, its chunks and downstream work."""
from __future__ import annotations

from app.tests._files_harness import (
    make_actor,
    make_graph,
    make_repo,
    outbound_payload,
    trigger_review,
)


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
