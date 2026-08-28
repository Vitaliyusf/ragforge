"""A review decision applies once, to the text the reviewer actually saw."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.errors import ValidationException
from app.utils.common import utcnow
from app.tests._files_harness import (
    make_actor,
    make_graph,
    make_repo,
    trigger_review,
)


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
