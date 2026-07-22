"""Graph-style orchestration for extraction review, chunking, and handoff."""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - optional dependency fallback
    END = "__end__"
    START = "__start__"
    StateGraph = None

from app.core.config import Settings
from app.core.errors import NotFoundException, ValidationException
from app.db.repository import FileRepository
from app.messaging.interfaces import IProducer
from app.services.graph_types import FilesLangSmithTracer, OutboundMessage
from app.services.issue_detector import IssueDetector
from app.utils.common import (
    apply_patch_map,
    build_message_envelope,
    build_preview,
    build_snippet,
    chunk_text as split_text_into_chunks,
    generate_decision_id,
    generate_event_id,
    generate_review_case_id,
    hash_text,
    make_resume_token,
    utcnow,
    validate_patch_map,
    validate_managed_file_path,
)
from shared.auth import identity_from_context


class FileIngestionGraph:
    """Coordinate extraction completion, review pause/resume, and chunk handoff.

    The graph persists state through Mongo-backed task documents, emits audit
    events around each major transition, and publishes downstream events only
    after the surrounding transaction completes.
    """

    def __init__(self, repository: FileRepository, producer: IProducer, logger, config: Settings):
        self.repository = repository
        self.producer = producer
        self.logger = logger
        self.config = config
        self.detector = IssueDetector(config)
        self.tracer = FilesLangSmithTracer(config)
        self._graph = self._build_graph()

    def _build_graph(self):
        if StateGraph is None:  # pragma: no cover - optional dependency fallback
            return None
        graph = StateGraph(dict)
        for node_name in (
            "load_extraction_result",
            "detect_issues",
            "create_review_case",
            "await_human_review",
            "apply_decision",
            "chunk_text",
            "request_embeddings",
            "finalize",
        ):
            graph.add_node(node_name, lambda state, _node=node_name: {"current_node": _node})
        graph.add_edge(START, "load_extraction_result")
        graph.add_edge("load_extraction_result", "detect_issues")
        graph.add_edge("detect_issues", "chunk_text")
        graph.add_edge("create_review_case", "await_human_review")
        graph.add_edge("apply_decision", "chunk_text")
        graph.add_edge("chunk_text", "request_embeddings")
        graph.add_edge("request_embeddings", "finalize")
        graph.add_edge("await_human_review", END)
        graph.add_edge("finalize", END)
        return graph.compile()

    def handle_extraction_completion(
        self,
        *,
        file_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        extracted_text: str,
        diagnostics: Optional[Dict[str, Any]],
        actor: Optional[Dict[str, Any]] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> List[OutboundMessage]:
        """Run the graph from extraction completion to pause or finalize.

        Args:
            file_doc: Current serialized file record.
            task_doc: Current serialized ingestion task record.
            extracted_text: Extracted text returned by the upstream extractor.
            diagnostics: Optional extractor diagnostics payload.
            actor: Actor metadata used for audit-event authorship.
            request_context: Request, trace, and reply metadata to merge into
                the persisted graph state.

        Returns:
            list[OutboundMessage]: Messages to publish after the transaction
            commits.

        Side effects:
            Updates file and task state, creates review cases when required,
            writes audit events, creates chunk documents, and prepares
            downstream event envelopes.
        """
        actor = actor or self._system_actor()
        with self.repository.transaction() as session:
            current_file = self.repository.get_raw_by_id(file_doc["file_id"], session=session)
            current_task = self.repository.get_raw_task_by_id(task_doc["task_id"], session=session)
            if current_file is None or current_task is None:
                raise NotFoundException("File task not found")

            state = dict(current_task.get("graph_state", {}))
            self._merge_request_context(state, request_context)
            with self.tracer.span("load_extraction_result", self._trace_metadata(current_file, current_task, state, None)):
                extracted_text_hash = hash_text(extracted_text)
                state.update(
                    {
                        "extracted_text": extracted_text,
                        "extracted_text_hash": extracted_text_hash,
                        "sanitized_text": None,
                        "sanitized_text_version": current_file.get("sanitized_text_version", 0),
                        "issue_findings": [],
                        "review_required": False,
                        "review_case_id": None,
                        "review_decision": None,
                        "redaction_patch_map": [],
                        "chunk_ids": [],
                        "embedding_job_ids": [],
                        "cleanup_required": False,
                        "error": None,
                    }
                )
                self.repository.update_file(
                    current_file["file_id"],
                    {
                        "document_id": current_file.get("document_id") or current_file["file_id"],
                        "current_task_id": current_task["task_id"],
                        "status": "processing",
                        "stage.extraction": "done",
                    },
                    session=session,
                )
                self.repository.update_task(
                    current_task["task_id"],
                    {
                        "status": "running",
                        "current_node": "detect_issues",
                        "graph_state": state,
                    },
                    session=session,
                )
                self._write_audit_event(
                    session=session,
                    file_doc=current_file,
                    task_doc=current_task,
                    event_type="extraction_completed",
                    actor=actor,
                    reason="Text extraction completed and graph processing started.",
                    details={"diagnostics": diagnostics or {}},
                    from_status="started",
                    to_status="processing",
                )

            with self.tracer.span("detect_issues", self._trace_metadata(current_file, current_task, state, None)):
                findings = self._enrich_findings(self.detector.detect(extracted_text, diagnostics or {}), extracted_text)
                state["issue_findings"] = findings
                review_required = any(item["score"] >= item["threshold"] for item in findings)
                state["review_required"] = review_required

            if review_required:
                return self._create_review_case(
                    session=session,
                    file_doc=current_file,
                    task_doc=current_task,
                    state=state,
                    actor=actor,
                )
            self.repository.update_file(
                current_file["file_id"],
                {
                    "status": "processing",
                    "review_status": "not_required",
                    "latest_review_case_id": None,
                    "stage.review": "done",
                },
                session=session,
            )
            self.repository.update_task(
                current_task["task_id"],
                {
                    "status": "running",
                    "current_node": "chunk_text",
                    "graph_state": state,
                },
                session=session,
            )
            return self._complete_chunking_flow(
                session=session,
                file_doc=current_file,
                task_doc=current_task,
                state=state,
                actor=actor,
                text_source="original",
                review_status="clean",
                issue_flags=[],
                redaction_applied=False,
            )

    def handle_review_decision(
        self,
        *,
        file_doc: Dict[str, Any],
        review_case_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        decision_payload: Dict[str, Any],
        actor: Dict[str, Any],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> List[OutboundMessage]:
        """Resume the graph from a submitted human review decision.

        Args:
            file_doc: Current serialized file record.
            review_case_doc: Serialized review-case document to resolve.
            task_doc: Current serialized task record.
            decision_payload: Human decision payload including
                `based_on_text_hash`.
            actor: Human or service actor metadata for audit events.
            request_context: Request, trace, and reply metadata to merge into
                the persisted graph state.

        Returns:
            list[OutboundMessage]: Messages to publish after the transaction
            commits.

        Errors:
            Raises `ValidationException` when the decision is stale, invalid,
            or incompatible with the review case.
        """
        with self.repository.transaction() as session:
            current_file = self.repository.get_raw_by_id(file_doc["file_id"], session=session)
            current_task = self.repository.get_raw_task_by_id(task_doc["task_id"], session=session)
            current_case = self.repository.get_raw_review_case_by_id(review_case_doc["review_case_id"], session=session)
            if current_file is None or current_task is None or current_case is None:
                raise NotFoundException("Review decision target not found")

            self._validate_review_decision(current_case, current_task, decision_payload)
            decision_id = generate_decision_id()
            resume_token_hash = current_task.get("resume_token_hash") or ""
            if not self.repository.claim_review_case(
                current_case["review_case_id"],
                extracted_text_hash=decision_payload["based_on_text_hash"],
                resume_token_hash=resume_token_hash,
                claim_id=decision_id,
                claimed_at=utcnow(),
                session=session,
            ):
                raise ValidationException("Review case is already being resolved")
            state = dict(current_task.get("graph_state", {}))
            self._merge_request_context(state, request_context)
            state["review_decision"] = decision_payload["decision"]
            state["review_case_id"] = current_case["review_case_id"]

            decision_doc = {
                "decision_id": decision_id,
                "review_case_id": current_case["review_case_id"],
                "file_id": current_file["file_id"],
                "document_id": current_file.get("document_id") or current_file["file_id"],
                "task_id": current_task["task_id"],
                "decision": decision_payload["decision"],
                "comment": decision_payload.get("comment", ""),
                "based_on_text_hash": decision_payload["based_on_text_hash"],
                "submitted_by": actor,
                "submitted_patch_map": decision_payload.get("patch_map", []),
                "created_at": utcnow(),
                **self._ownership(current_file),
            }
            self.repository.create_review_decision(decision_doc, session=session)
            self.repository.update_review_case(
                current_case["review_case_id"],
                {
                    "status": "resolved",
                    "decision_status": decision_payload["decision"],
                    "resolved_at": utcnow(),
                    "resolved_by": actor,
                    "graph_interrupt.resume_token_hash": None,
                    "graph_interrupt.resume_token_expires_at": None,
                },
                session=session,
            )
            self.repository.update_task(
                current_task["task_id"],
                {
                    "status": "resuming",
                    "current_node": "apply_decision",
                    "checkpoint_id": None,
                    "resume_token_hash": None,
                    "resume_token_expires_at": None,
                    "graph_state": state,
                },
                session=session,
            )
            self._write_audit_event(
                session=session,
                file_doc=current_file,
                task_doc=current_task,
                event_type="review_decision_submitted",
                actor=actor,
                reason="A human review decision was submitted.",
                details={"decision": decision_payload["decision"]},
                review_case_id=current_case["review_case_id"],
                decision_id=decision_id,
            )
            self._write_audit_event(
                session=session,
                file_doc=current_file,
                task_doc=current_task,
                event_type="graph_resumed",
                actor=actor,
                reason="Graph resumed after human review decision.",
                details={"decision": decision_payload["decision"]},
                review_case_id=current_case["review_case_id"],
                decision_id=decision_id,
            )

            if decision_payload["decision"] == "delete_file":
                return self._apply_delete_decision(
                    session=session,
                    file_doc=current_file,
                    task_doc=current_task,
                    review_case_doc=current_case,
                    state=state,
                    actor=actor,
                    decision_id=decision_id,
                )
            if decision_payload["decision"] == "remove_problematic_text":
                return self._apply_redaction_decision(
                    session=session,
                    file_doc=current_file,
                    task_doc=current_task,
                    review_case_doc=current_case,
                    state=state,
                    actor=actor,
                    decision_id=decision_id,
                    patch_map=decision_payload["patch_map"],
                )
            return self._apply_accept_decision(
                session=session,
                file_doc=current_file,
                task_doc=current_task,
                review_case_doc=current_case,
                state=state,
                actor=actor,
                decision_id=decision_id,
            )

    def _create_review_case(
        self,
        *,
        session,
        file_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        state: Dict[str, Any],
        actor: Dict[str, Any],
    ) -> List[OutboundMessage]:
        findings = state["issue_findings"]
        highest_finding = max(findings, key=lambda item: item["score"])
        review_case_id = generate_review_case_id()
        checkpoint_id = f"checkpoint-{review_case_id}"
        resume_token = make_resume_token(self.config.review_resume_token_ttl_seconds)
        allowed_actions = ["delete_file", "remove_problematic_text", "accept_as_is"]
        review_case_doc = {
            "review_case_id": review_case_id,
            "file_id": file_doc["file_id"],
            "document_id": file_doc.get("document_id") or file_doc["file_id"],
            "task_id": task_doc["task_id"],
            "status": "open",
            "decision_status": "pending",
            "highest_severity_score": highest_finding["score"],
            "extracted_text_hash": state["extracted_text_hash"],
            "problem_description": highest_finding["problem_description"],
            "problematic_text": highest_finding["problematic_text"],
            "why_problematic": highest_finding["why_problematic"],
            "issue_categories": findings,
            "allowed_actions": allowed_actions,
            "redaction_patch_map": self._default_patch_map(findings),
            "graph_interrupt": {
                "graph_run_id": task_doc["graph_run_id"],
                "checkpoint_id": checkpoint_id,
                "resume_token_hash": resume_token["token_hash"],
                "resume_token_expires_at": resume_token["expires_at"],
            },
            "opened_at": utcnow(),
            "resolved_at": None,
            "resolved_by": {
                "actor_id": None,
                "actor_type": None,
                "display_name": None,
            },
            **self._ownership(file_doc),
        }
        state["review_required"] = True
        state["review_case_id"] = review_case_id
        state["redaction_patch_map"] = review_case_doc["redaction_patch_map"]
        self.repository.create_review_case(review_case_doc, session=session)
        self.repository.update_file(
            file_doc["file_id"],
            {
                "status": "awaiting_review",
                "review_status": "pending",
                "latest_review_case_id": review_case_id,
                "current_task_id": task_doc["task_id"],
                "stage.review": "paused",
            },
            session=session,
        )
        self.repository.update_task(
            task_doc["task_id"],
            {
                "status": "waiting_for_review",
                "current_node": "await_human_review",
                "checkpoint_id": checkpoint_id,
                "resume_token_hash": resume_token["token_hash"],
                "resume_token_expires_at": resume_token["expires_at"],
                "graph_state": state,
            },
            session=session,
        )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="issue_detected",
            actor=actor,
            reason="One or more issue detectors exceeded the configured threshold.",
            details={"issue_categories": [item["category"] for item in findings]},
            review_case_id=review_case_id,
            from_status="processing",
            to_status="awaiting_review",
        )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="review_case_created",
            actor=actor,
            reason="A review case was created for human approval.",
            details={"allowed_actions": allowed_actions},
            review_case_id=review_case_id,
            from_status="processing",
            to_status="awaiting_review",
        )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="ingestion_paused_for_review",
            actor=actor,
            reason="Ingestion paused pending human review.",
            details={"checkpoint_id": checkpoint_id},
            review_case_id=review_case_id,
            from_status="processing",
            to_status="awaiting_review",
        )
        return [
            OutboundMessage(
                self.config.files_events_topic,
                self._build_outbound_envelope(
                    state=state,
                    message_type="event",
                    action="files.review.required",
                    target_service="gateway",
                    payload={
                        "event_id": generate_event_id(),
                        "event_type": "files.review.required",
                        "file_id": file_doc["file_id"],
                        "document_id": file_doc.get("document_id") or file_doc["file_id"],
                        "task_id": task_doc["task_id"],
                        "review_case_id": review_case_id,
                        "status": "awaiting_review",
                        "review_status": "pending",
                        "issue_categories": [item["category"] for item in findings],
                        "highest_severity_score": highest_finding["score"],
                        "allowed_actions": allowed_actions,
                        "created_at": utcnow().isoformat(),
                    },
                ),
            )
        ]

    def _apply_delete_decision(
        self,
        *,
        session,
        file_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        review_case_doc: Dict[str, Any],
        state: Dict[str, Any],
        actor: Dict[str, Any],
        decision_id: str,
    ) -> List[OutboundMessage]:
        deleted_chunks = self.repository.delete_chunks_for_file(file_doc["file_id"], session=session)
        stored_path = None
        if file_doc.get("path"):
            identity = identity_from_context()
            try:
                stored_path = str(validate_managed_file_path(
                    self.config.upload_dir,
                    identity.tenant_id,
                    file_doc["file_id"],
                    file_doc["path"],
                ))
            except ValueError as exc:
                raise ValidationException(str(exc)) from exc
        if stored_path and os.path.exists(stored_path):
            try:
                os.remove(stored_path)
            except OSError:
                pass
        has_cleanup = deleted_chunks > 0 or file_doc.get("stage", {}).get("chunking") == "done"
        state["review_decision"] = "delete_file"
        state["cleanup_required"] = has_cleanup
        state["extracted_text"] = None
        state["sanitized_text"] = None
        state["chunk_ids"] = []
        state["embedding_job_ids"] = []
        self.repository.update_file(
            file_doc["file_id"],
            {
                "status": "rejected",
                "review_status": "rejected",
                "stage.review": "done",
                "stage.chunking": "skipped",
                "stage.embedding": "skipped",
            },
            session=session,
        )
        self.repository.update_task(
            task_doc["task_id"],
            {
                "status": "rejected",
                "current_node": "finalize",
                "completed_at": utcnow(),
                "graph_state": state,
            },
            session=session,
        )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="file_rejected",
            actor=actor,
            reason="The file was rejected during human review.",
            details={"deleted_chunks": deleted_chunks},
            review_case_id=review_case_doc["review_case_id"],
            decision_id=decision_id,
            from_status="awaiting_review",
            to_status="rejected",
        )
        outbound: List[OutboundMessage] = []
        if has_cleanup:
            outbound.append(
                OutboundMessage(
                    self.config.vector_db_delete_topic,
                    self._build_outbound_envelope(
                        state=state,
                        message_type="event",
                        action="vector_db.delete.requested",
                        target_service="vector_db",
                        payload={
                            "event_id": generate_event_id(),
                            "event_type": "vector_db.delete.requested",
                            "file_id": file_doc["file_id"],
                            "document_id": file_doc.get("document_id") or file_doc["file_id"],
                            "task_id": task_doc["task_id"],
                            "reason": "review_delete_file",
                            "delete_chunks": True,
                            "delete_vectors": True,
                            "created_at": utcnow().isoformat(),
                        },
                    ),
                )
            )
            self._write_audit_event(
                session=session,
                file_doc=file_doc,
                task_doc=task_doc,
                event_type="vector_delete_requested",
                actor=actor,
                reason="Vector cleanup requested after review rejection.",
                details={"reason": "review_delete_file"},
                review_case_id=review_case_doc["review_case_id"],
                decision_id=decision_id,
            )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="cleanup_completed",
            actor=actor,
            reason="Review rejection cleanup completed.",
            details={"deleted_chunks": deleted_chunks},
            review_case_id=review_case_doc["review_case_id"],
            decision_id=decision_id,
        )
        return outbound

    def _apply_redaction_decision(
        self,
        *,
        session,
        file_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        review_case_doc: Dict[str, Any],
        state: Dict[str, Any],
        actor: Dict[str, Any],
        decision_id: str,
        patch_map: List[Dict[str, Any]],
    ) -> List[OutboundMessage]:
        extracted_text = state.get("extracted_text") or ""
        validate_patch_map(extracted_text, patch_map)
        sanitized_text = apply_patch_map(extracted_text, patch_map)
        sanitized_version = int(file_doc.get("sanitized_text_version", 0)) + 1
        state["sanitized_text"] = sanitized_text
        state["sanitized_text_version"] = sanitized_version
        state["redaction_patch_map"] = patch_map
        self.repository.update_file(
            file_doc["file_id"],
            {
                "review_status": "approved_sanitized",
                "status": "processing",
                "sanitized_text_version": sanitized_version,
                "stage.review": "done",
            },
            session=session,
        )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="file_sanitized",
            actor=actor,
            reason="Problematic text was redacted and ingestion resumed.",
            details={"sanitized_text_version": sanitized_version},
            review_case_id=review_case_doc["review_case_id"],
            decision_id=decision_id,
            from_status="awaiting_review",
            to_status="processing",
        )
        return self._complete_chunking_flow(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            state=state,
            actor=actor,
            text_source="sanitized",
            review_status="sanitized",
            issue_flags=self._issue_categories(review_case_doc),
            redaction_applied=True,
            review_case_id=review_case_doc["review_case_id"],
            decision_id=decision_id,
        )

    def _apply_accept_decision(
        self,
        *,
        session,
        file_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        review_case_doc: Dict[str, Any],
        state: Dict[str, Any],
        actor: Dict[str, Any],
        decision_id: str,
    ) -> List[OutboundMessage]:
        categories = self._issue_categories(review_case_doc)
        self.repository.update_file(
            file_doc["file_id"],
            {
                "review_status": "approved_as_is",
                "status": "processing",
                "accepted_risk_categories": categories,
                "stage.review": "done",
            },
            session=session,
        )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="file_accepted_with_risk",
            actor=actor,
            reason="The file was accepted as-is after human review.",
            details={"accepted_risk_categories": categories},
            review_case_id=review_case_doc["review_case_id"],
            decision_id=decision_id,
            from_status="awaiting_review",
            to_status="processing",
        )
        return self._complete_chunking_flow(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            state=state,
            actor=actor,
            text_source="original",
            review_status="accepted_with_risk",
            issue_flags=categories,
            redaction_applied=False,
            review_case_id=review_case_doc["review_case_id"],
            decision_id=decision_id,
        )

    def _complete_chunking_flow(
        self,
        *,
        session,
        file_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        state: Dict[str, Any],
        actor: Dict[str, Any],
        text_source: str,
        review_status: str,
        issue_flags: List[str],
        redaction_applied: bool,
        review_case_id: Optional[str] = None,
        decision_id: Optional[str] = None,
    ) -> List[OutboundMessage]:
        source_text = state.get("sanitized_text") if text_source == "sanitized" else state.get("extracted_text")
        source_text = source_text or ""
        chunk_version = self.repository.get_next_chunk_version(file_doc.get("document_id") or file_doc["file_id"])
        chunk_docs = self._build_chunk_documents(
            file_doc=file_doc,
            task_id=task_doc["task_id"],
            text=source_text,
            text_source=text_source,
            review_status=review_status,
            issue_flags=issue_flags,
            redaction_applied=redaction_applied,
            chunk_version=chunk_version,
        )
        created_count = self.repository.create_chunks(chunk_docs, session=session)
        state["chunk_ids"] = [chunk["chunk_id"] for chunk in chunk_docs]
        embedding_event_id = generate_event_id()
        state["embedding_job_ids"] = [embedding_event_id]
        self.repository.update_file(
            file_doc["file_id"],
            {
                "status": "processing",
                "stage.review": "done",
                "stage.chunking": "done",
                "stage.embedding": "running",
            },
            session=session,
        )
        self.repository.update_task(
            task_doc["task_id"],
            {
                "status": "completed",
                "current_node": "finalize",
                "completed_at": utcnow(),
                "graph_state": state,
            },
            session=session,
        )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="chunking_completed",
            actor=actor,
            reason="File text was chunked for embedding.",
            details={"chunk_count": created_count, "text_source": text_source},
            review_case_id=review_case_id,
            decision_id=decision_id,
        )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="embedding_jobs_requested",
            actor=actor,
            reason="Embedding jobs were requested for file chunks.",
            details={"chunk_count": len(chunk_docs), "text_source": text_source},
            review_case_id=review_case_id,
            decision_id=decision_id,
        )
        self._write_audit_event(
            session=session,
            file_doc=file_doc,
            task_doc=task_doc,
            event_type="ingestion_completed",
            actor=actor,
            reason="The file ingestion graph completed and handed off downstream processing.",
            details={"task_status": "completed"},
            review_case_id=review_case_id,
            decision_id=decision_id,
        )
        return [
            OutboundMessage(
                self.config.files_events_topic,
                self._build_outbound_envelope(
                    state=state,
                    message_type="event",
                    action="files.chunking.completed",
                    target_service="gateway",
                    payload={
                        "event_id": generate_event_id(),
                        "event_type": "files.chunking.completed",
                        "file_id": file_doc["file_id"],
                        "document_id": file_doc.get("document_id") or file_doc["file_id"],
                        "task_id": task_doc["task_id"],
                        "chunk_count": len(chunk_docs),
                        "text_source": text_source,
                        "review_case_id": review_case_id,
                        "created_at": utcnow().isoformat(),
                    },
                ),
            ),
            OutboundMessage(
                self.config.embedding_jobs_topic,
                self._build_outbound_envelope(
                    state=state,
                    message_type="command",
                    action="process_embedding_job",
                    target_service="embedding",
                    payload={
                        "job_id": embedding_event_id,
                        "file_id": file_doc["file_id"],
                        "document_id": file_doc.get("document_id") or file_doc["file_id"],
                        "requested_at": utcnow().isoformat(),
                        "chunks": [self._chunk_event_payload(chunk_doc) for chunk_doc in chunk_docs],
                    },
                ),
            ),
        ]

    def _validate_review_decision(
        self,
        review_case_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        decision_payload: Dict[str, Any],
    ) -> None:
        if review_case_doc.get("status") != "open":
            raise ValidationException("Review case is not active")
        if review_case_doc.get("decision_status") != "pending":
            raise ValidationException("Review case already has a decision")
        if decision_payload.get("based_on_text_hash") != review_case_doc.get("extracted_text_hash"):
            raise ValidationException("based_on_text_hash does not match extracted text")
        expires_at = review_case_doc.get("graph_interrupt", {}).get("resume_token_expires_at")
        if expires_at is not None and expires_at <= utcnow():
            raise ValidationException("Review resume token has expired")
        if not task_doc.get("resume_token_hash"):
            raise ValidationException("Review resume token has already been consumed")
        decision = decision_payload.get("decision")
        if decision not in set(review_case_doc.get("allowed_actions", [])):
            raise ValidationException("Decision is not allowed for this review case")
        patch_map = decision_payload.get("patch_map") or []
        if decision == "remove_problematic_text" and not patch_map:
            raise ValidationException("patch_map is required for remove_problematic_text")
        if decision in {"delete_file", "accept_as_is"} and patch_map:
            raise ValidationException("patch_map is not allowed for this decision")

    def _enrich_findings(self, findings: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for finding in findings:
            span = finding.get("text_span", {"start": 0, "end": 0})
            enriched.append(
                {
                    **finding,
                    "problematic_text": build_snippet(
                        text,
                        span.get("start", 0),
                        span.get("end", 0),
                        self.config.review_snippet_max_chars,
                    ),
                }
            )
        return enriched

    def _default_patch_map(self, findings: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        patch_map: List[Dict[str, Any]] = []
        for index, finding in enumerate(findings):
            span = finding.get("text_span", {})
            start = span.get("start", 0)
            end = span.get("end", 0)
            if end <= start:
                continue
            patch_map.append(
                {
                    "patch_id": f"default-patch-{index}",
                    "action": "replace",
                    "start": start,
                    "end": end,
                    "replacement": f"[REDACTED_{finding['category'].upper()}]",
                    "reason": finding["category"],
                }
            )
        return patch_map

    def _build_chunk_documents(
        self,
        *,
        file_doc: Dict[str, Any],
        task_id: str,
        text: str,
        text_source: str,
        review_status: str,
        issue_flags: List[str],
        redaction_applied: bool,
        chunk_version: int,
    ) -> List[Dict[str, Any]]:
        document_id = file_doc.get("document_id") or file_doc["file_id"]
        spans = split_text_into_chunks(text, self.config.chunk_size, self.config.chunk_overlap)
        now = utcnow()
        chunk_docs: List[Dict[str, Any]] = []
        for index, span in enumerate(spans):
            chunk_body = text[span["char_start"]:span["char_end"]]
            source_name = file_doc["filename"]
            page = None
            section = None
            chunk_docs.append(
                {
                    "chunk_id": f"{document_id}__v{chunk_version}__c{index}",
                    "file_id": file_doc["file_id"],
                    "document_id": document_id,
                    "task_id": task_id,
                    "chunk_index": index,
                    "chunk_version": chunk_version,
                    "text": chunk_body,
                    "text_preview": build_preview(chunk_body, self.config.chunk_preview_max_chars),
                    "text_source": text_source,
                    "char_start": span["char_start"],
                    "char_end": span["char_end"],
                    "source_name": source_name,
                    "page": page,
                    "section": section,
                    "metadata": {
                        "page": page,
                        "section": section,
                        "source_name": source_name,
                    },
                    "review_status": review_status,
                    "retrieval_allowed": review_status != "removed",
                    "issue_flags": list(issue_flags),
                    "redaction_applied": redaction_applied,
                    "created_at": now,
                    "updated_at": now,
                    **self._ownership(file_doc),
                }
            )
        return chunk_docs

    def _chunk_event_payload(self, chunk_doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "file_id": chunk_doc["file_id"],
            "document_id": chunk_doc["document_id"],
            "chunk_id": chunk_doc["chunk_id"],
            "chunk_index": chunk_doc["chunk_index"],
            "chunk_version": chunk_doc["chunk_version"],
            "text": chunk_doc["text"],
            "text_preview": chunk_doc["text_preview"],
            "source_name": chunk_doc.get("source_name") or chunk_doc["metadata"]["source_name"],
            "page": chunk_doc.get("page", chunk_doc["metadata"].get("page")),
            "section": chunk_doc.get("section", chunk_doc["metadata"].get("section")),
            "review_status": chunk_doc["review_status"],
            "retrieval_allowed": chunk_doc["retrieval_allowed"],
            "issue_flags": chunk_doc["issue_flags"],
            "created_at": chunk_doc["created_at"].isoformat(),
            "text_source": chunk_doc["text_source"],
            "char_start": chunk_doc["char_start"],
            "char_end": chunk_doc["char_end"],
            "redaction_applied": chunk_doc["redaction_applied"],
            "updated_at": chunk_doc["updated_at"].isoformat(),
            "metadata": {
                "file_id": chunk_doc["file_id"],
                "document_id": chunk_doc["document_id"],
                "source_name": chunk_doc.get("source_name") or chunk_doc["metadata"]["source_name"],
                "page": chunk_doc.get("page", chunk_doc["metadata"].get("page")),
                "section": chunk_doc.get("section", chunk_doc["metadata"].get("section")),
                "tenant_id": chunk_doc.get("tenant_id"),
                "owner_user_id": chunk_doc.get("owner_user_id"),
                "owner_admin_id": chunk_doc.get("owner_admin_id"),
            },
            "tenant_id": chunk_doc.get("tenant_id"),
            "owner_user_id": chunk_doc.get("owner_user_id"),
            "owner_admin_id": chunk_doc.get("owner_admin_id"),
        }

    def _merge_request_context(
        self,
        state: Dict[str, Any],
        request_context: Optional[Dict[str, Any]],
    ) -> None:
        if not request_context:
            return
        for key in ("request_id", "trace_id", "correlation_id", "source_service", "reply_to", "stream_to"):
            value = request_context.get(key)
            if value is not None:
                state[key] = value

    def _build_outbound_envelope(
        self,
        *,
        state: Dict[str, Any],
        message_type: str,
        action: str,
        target_service: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return build_message_envelope(
            message_type=message_type,
            action=action,
            source_service=getattr(self.config, "service_name", "files"),
            target_service=target_service,
            request_id=state.get("request_id"),
            trace_id=state.get("trace_id"),
            correlation_id=state.get("correlation_id"),
            payload=payload,
        )

    def _write_audit_event(
        self,
        *,
        session,
        file_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        event_type: str,
        actor: Dict[str, Any],
        reason: str,
        details: Dict[str, Any],
        review_case_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
    ) -> None:
        self.repository.insert_audit_event(
            {
                "event_id": generate_event_id(),
                "file_id": file_doc["file_id"],
                "document_id": file_doc.get("document_id") or file_doc["file_id"],
                "task_id": task_doc.get("task_id"),
                "review_case_id": review_case_id,
                "decision_id": decision_id,
                "event_type": event_type,
                "from_status": from_status,
                "to_status": to_status,
                "actor": actor,
                "reason": reason,
                "details": details,
                "file_ref": {
                    "db": "files",
                    "collection": "files",
                    "file_id": file_doc["file_id"],
                    "document_id": file_doc.get("document_id") or file_doc["file_id"],
                    "filename": file_doc["filename"],
                },
                "created_at": utcnow(),
                **self._ownership(file_doc),
            },
            session=session,
        )

    @staticmethod
    def _ownership(file_doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: file_doc[key]
            for key in ("tenant_id", "owner_user_id", "owner_admin_id")
            if file_doc.get(key) is not None
        }

    def _issue_categories(self, review_case_doc: Dict[str, Any]) -> List[str]:
        categories: List[str] = []
        seen = set()
        for finding in review_case_doc.get("issue_categories", []):
            category = finding.get("category")
            if category and category not in seen:
                seen.add(category)
                categories.append(category)
        return categories

    def _trace_metadata(
        self,
        file_doc: Dict[str, Any],
        task_doc: Dict[str, Any],
        state: Dict[str, Any],
        review_case_id: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "service": "files",
            "request_id": state.get("request_id"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "graph_run_id": task_doc.get("graph_run_id"),
            "file_id": file_doc["file_id"],
            "document_id": file_doc.get("document_id") or file_doc["file_id"],
            "task_id": task_doc.get("task_id"),
            "review_case_id": review_case_id or state.get("review_case_id"),
            "current_node": task_doc.get("current_node"),
            "review_status": file_doc.get("review_status"),
            "decision_status": state.get("review_decision"),
        }

    @staticmethod
    def _system_actor() -> Dict[str, Any]:
        return {
            "actor_id": "files",
            "actor_type": "service",
            "display_name": "files",
        }
