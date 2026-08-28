"""Explicit states and allowed transitions for file ingestion."""
from __future__ import annotations

from typing import Any, Dict, FrozenSet

from app.core.constants import IngestionState
from app.utils.common import utcnow


ALLOWED_INGESTION_TRANSITIONS: Dict[IngestionState, FrozenSet[IngestionState]] = {
    IngestionState.LOAD_EXTRACTION_RESULT: frozenset({IngestionState.DETECT_ISSUES}),
    IngestionState.DETECT_ISSUES: frozenset(
        {IngestionState.AWAIT_HUMAN_REVIEW, IngestionState.CHUNK_TEXT}
    ),
    IngestionState.AWAIT_HUMAN_REVIEW: frozenset({IngestionState.APPLY_DECISION}),
    IngestionState.APPLY_DECISION: frozenset(
        {IngestionState.CHUNK_TEXT, IngestionState.FINALIZE}
    ),
    IngestionState.CHUNK_TEXT: frozenset({IngestionState.REQUEST_EMBEDDINGS}),
    IngestionState.REQUEST_EMBEDDINGS: frozenset({IngestionState.FINALIZE}),
    IngestionState.FINALIZE: frozenset(),
}


def transition_ingestion_state(current: str, target: IngestionState) -> str:
    """Validate and return one deterministic ingestion transition."""
    try:
        current_state = IngestionState(current)
    except ValueError as exc:
        raise ValueError(f"Unknown ingestion state: {current}") from exc
    if target not in ALLOWED_INGESTION_TRANSITIONS[current_state]:
        raise ValueError(
            f"Invalid ingestion transition: {current_state.value} -> {target.value}"
        )
    return target.value


class IngestionTaskTransitions:
    """Persist domain-named ingestion transitions on task documents."""

    def __init__(self, repository) -> None:
        self.repository = repository

    def begin_issue_detection(self, session, task_doc: Dict[str, Any], state: Dict[str, Any]) -> None:
        self._transition(session, task_doc, state, IngestionState.DETECT_ISSUES, status="running")

    def pause_for_review(
        self,
        session,
        task_doc: Dict[str, Any],
        state: Dict[str, Any],
        *,
        checkpoint_id: str,
        resume_token: Dict[str, Any],
    ) -> None:
        self._transition(
            session,
            task_doc,
            state,
            IngestionState.AWAIT_HUMAN_REVIEW,
            status="waiting_for_review",
            checkpoint_id=checkpoint_id,
            resume_token_hash=resume_token["token_hash"],
            resume_token_expires_at=resume_token["expires_at"],
        )

    def resume_review(self, session, task_doc: Dict[str, Any], state: Dict[str, Any]) -> None:
        self._transition(
            session,
            task_doc,
            state,
            IngestionState.APPLY_DECISION,
            status="resuming",
            checkpoint_id=None,
            resume_token_hash=None,
            resume_token_expires_at=None,
        )

    def begin_chunking(self, session, task_doc: Dict[str, Any], state: Dict[str, Any]) -> None:
        self._transition(session, task_doc, state, IngestionState.CHUNK_TEXT, status="running")

    def request_embeddings(self, session, task_doc: Dict[str, Any], state: Dict[str, Any]) -> None:
        self._transition(
            session,
            task_doc,
            state,
            IngestionState.REQUEST_EMBEDDINGS,
            status="running",
        )

    def finalize(self, session, task_doc: Dict[str, Any], state: Dict[str, Any]) -> None:
        self._transition(
            session,
            task_doc,
            state,
            IngestionState.FINALIZE,
            status="completed",
            completed_at=utcnow(),
        )

    def finalize_rejected(self, session, task_doc: Dict[str, Any], state: Dict[str, Any]) -> None:
        self._transition(
            session,
            task_doc,
            state,
            IngestionState.FINALIZE,
            status="rejected",
            completed_at=utcnow(),
        )

    def _transition(
        self,
        session,
        task_doc: Dict[str, Any],
        state: Dict[str, Any],
        target: IngestionState,
        **updates: Any,
    ) -> None:
        next_state = transition_ingestion_state(task_doc["current_node"], target)
        task_updates = {**updates, "current_node": next_state, "graph_state": state}
        self.repository.update_task(task_doc["task_id"], task_updates, session=session)
        task_doc.update(task_updates)
