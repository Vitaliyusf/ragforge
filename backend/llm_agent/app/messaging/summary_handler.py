"""File-summarisation RabbitMQ handler."""
from typing import Any, Dict

from app.messaging.base_handler import BaseRabbitMQHandler
from app.messaging.interfaces import IProducer
from app.core.config import Settings
from app.core.constants import FilesAction
from app.core.logging_config import ServiceLogger
from app.services.summary_service import SummaryService

try:
    from shared.schemas.message_schemas import SummaryRequest
    _HAS_SCHEMAS = True
except ImportError:
    _HAS_SCHEMAS = False


class SummaryHandler(BaseRabbitMQHandler):
    """Handle file-summarisation requests (fire-and-forget pipeline stage)."""

    def __init__(
        self,
        producer: IProducer,
        summary_service: SummaryService,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        super().__init__(producer, logger, config)
        self.summary_service = summary_service

    def handle(self, message: Dict[str, Any]) -> None:
        if _HAS_SCHEMAS:
            validated, error = self._validate(message, SummaryRequest)
            if error:
                self.logger.log("rabbitmq:summary", "Schema validation failed, skipping", {"error": error}, hypothesis_id="E")
                return

        file_id = message.get("file_id", "")
        text = message.get("text", "")
        prompt_prefix = message.get("prompt", "TL;DR")
        model = message.get("model")

        self.logger.log(
            "rabbitmq:summary",
            "Processing summary request",
            {"file_id": file_id, "text_length": len(text), "model": model},
        )

        try:
            summary = self.summary_service.generate_summary(text, model, prompt_prefix)
            self._fire_and_forget(
                self.config.files_queue,
                {"action": FilesAction.UPDATE_SUMMARY, "file_id": file_id, "summary": summary},
            )
            self.logger.log(
                "rabbitmq:summary",
                "Summary generated and sent",
                {"file_id": file_id, "summary_length": len(summary)},
            )
        except Exception as e:
            error_str = str(e)
            is_timeout = "timeout" in error_str.lower() or "timed out" in error_str.lower()
            is_model_error = "failed to load" in error_str.lower() or "unknown task" in error_str.lower()

            error_type = (
                "timeout" if is_timeout
                else "model_error" if is_model_error
                else "generation_error"
            )
            self.logger.log(
                "rabbitmq:summary",
                f"Error generating summary ({error_type})",
                {"file_id": file_id, "error": error_str},
                hypothesis_id="E",
            )

            if is_timeout:
                error_summary = "Summary generation timed out. The model may be too slow for this text length."
            elif is_model_error:
                error_summary = f"Model error: {error_str[:200]}. The model may not be suitable for summarisation."
            else:
                short = error_str[:200] + "..." if len(error_str) > 200 else error_str
                error_summary = f"Error generating summary: {short}"

            self._fire_and_forget(
                self.config.files_queue,
                {"action": FilesAction.UPDATE_SUMMARY, "file_id": file_id, "summary": error_summary},
            )
