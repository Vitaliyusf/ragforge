"""File update handlers for ingestion pipeline events."""
from __future__ import annotations

from typing import Any, Dict


class FileUpdateMixin:
    """Handle fire-and-forget file update actions from downstream services."""

    def handle_update_stage(self, request: Dict[str, Any]) -> None:
        """Handle fire-and-forget stage updates."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        stage_name = payload.get("stage")
        stage_status = payload.get("status")
        if not file_id or not stage_name:
            return
        if self.repository.update_stage(file_id, stage_name, stage_status):
            self._check_and_update_overall_status(file_id)

    def handle_update_summary(self, request: Dict[str, Any]) -> None:
        """Handle summary updates."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        summary = payload.get("summary", "")
        if file_id and self.repository.update_summary(file_id, summary):
            self._check_and_update_overall_status(file_id)

    def handle_update_suggested_questions(self, request: Dict[str, Any]) -> None:
        """Handle suggested question updates."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        questions = payload.get("questions", [])
        if file_id and isinstance(questions, list):
            self.repository.update_suggested_questions(file_id, questions)

    def handle_update_metadata(self, request: Dict[str, Any]) -> None:
        """Handle metadata updates."""
        payload = self._payload(request)
        file_id = payload.get("file_id")
        keywords = payload.get("keywords", [])
        if file_id and isinstance(keywords, list) and self.repository.update_metadata(file_id, keywords):
            self._check_and_update_overall_status(file_id)
