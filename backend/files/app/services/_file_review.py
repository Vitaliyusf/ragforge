"""File review and audit-trail request handlers."""
from __future__ import annotations

from typing import Any, Dict


class FileReviewMixin:
    """Handle review case and audit trail actions."""

    def handle_get_review_case(self, correlation_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch the active review case for a file and reply to the caller."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        if not file_id:
            return self._send_error(correlation_id, "file_id is required", request=request, reply_topic=request.get("reply_to"))

        review_case = self.repository.get_open_review_case_for_file(file_id)
        if not review_case:
            return self._send_error(correlation_id, "Active review case not found", request=request, reply_topic=request.get("reply_to"))

        return self._send_response(
            correlation_id,
            {
                "file_id": review_case["file_id"],
                "review_case_id": review_case["review_case_id"],
                "status": review_case["status"],
                "decision_status": review_case["decision_status"],
                "problem_description": review_case["problem_description"],
                "problematic_text": review_case["problematic_text"],
                "why_problematic": review_case["why_problematic"],
                "extracted_text_hash": review_case.get("extracted_text_hash"),
                "issue_categories": review_case.get("issue_categories", []),
                "allowed_actions": review_case.get("allowed_actions", []),
                "redaction_patch_map": review_case.get("redaction_patch_map", []),
                "opened_at": review_case.get("opened_at"),
            },
            request=request,
            reply_topic=request.get("reply_to"),
        )

    def handle_submit_review_decision(self, correlation_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a human review decision and resume ingestion."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        review_case_id = payload.get("review_case_id")
        if not file_id or not review_case_id:
            return self._send_error(
                correlation_id,
                "file_id and review_case_id are required",
                request=request,
                reply_topic=request.get("reply_to"),
            )

        file_doc = self.repository.get_by_id(file_id)
        review_case = self.repository.get_review_case_by_id(review_case_id)
        if not file_doc or not review_case:
            return self._send_error(correlation_id, "Review case not found", request=request, reply_topic=request.get("reply_to"))

        task_id = file_doc.get("current_task_id") or review_case.get("task_id")
        task_doc = self.repository.get_task_by_id(task_id) if task_id else None
        if task_doc is None:
            return self._send_error(correlation_id, "File task not found", request=request, reply_topic=request.get("reply_to"))

        try:
            outbound = self.state_machine.handle_review_decision(
                file_doc=file_doc,
                review_case_doc=review_case,
                task_doc=task_doc,
                decision_payload=payload,
                actor=self._actor(request),
                request_context=self._request_context(request),
            )
        except Exception as exc:
            self._write_ingestion_failure_event(
                file_doc,
                task_doc,
                self._actor(request),
                exc,
                review_case_id=review_case_id,
            )
            raise
        self._publish_messages(outbound)
        refreshed_file = self.repository.get_by_id(file_id) or file_doc
        latest_decision = self.repository.get_latest_review_decision(review_case_id)
        latest_task = self.repository.get_task_by_id(task_id)
        return self._send_response(
            correlation_id,
            {
                "file_id": file_id,
                "review_case_id": review_case_id,
                "decision_id": latest_decision.get("decision_id") if latest_decision else None,
                "decision": payload["decision"],
                "file_status": refreshed_file.get("status"),
                "review_status": refreshed_file.get("review_status"),
                "task_status": latest_task.get("status") if latest_task else None,
            },
            request=request,
            reply_topic=request.get("reply_to"),
        )

    def handle_get_audit_trail(self, correlation_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch paginated audit events for a file and reply with a cursor."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        if not file_id:
            return self._send_error(correlation_id, "file_id is required", request=request, reply_topic=request.get("reply_to"))
        limit = int(payload.get("limit") or 50)
        cursor = payload.get("cursor")
        events, next_cursor = self.repository.get_audit_events(file_id, limit=limit, cursor=cursor)
        return self._send_response(
            correlation_id,
            {"file_id": file_id, "events": events, "next_cursor": next_cursor},
            request=request,
            reply_topic=request.get("reply_to"),
        )
