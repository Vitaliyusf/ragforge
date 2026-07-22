"""Keyword-extraction RabbitMQ handler."""
from typing import Any, Dict

from app.messaging.base_handler import BaseRabbitMQHandler
from app.messaging.interfaces import IProducer
from app.core.config import Settings
from app.core.constants import FilesAction
from app.core.logging_config import ServiceLogger
from app.services.metadata_service import MetadataService

try:
    from shared.schemas.message_schemas import MetadataRequest
    _HAS_SCHEMAS = True
except ImportError:
    _HAS_SCHEMAS = False


class MetadataHandler(BaseRabbitMQHandler):
    """Handle keyword-extraction requests (fire-and-forget pipeline stage)."""

    def __init__(
        self,
        producer: IProducer,
        metadata_service: MetadataService,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        super().__init__(producer, logger, config)
        self.metadata_service = metadata_service

    def handle(self, message: Dict[str, Any]) -> None:
        if _HAS_SCHEMAS:
            validated, error = self._validate(message, MetadataRequest)
            if error:
                self.logger.log("rabbitmq:metadata", "Schema validation failed, skipping", {"error": error}, hypothesis_id="E")
                return

        file_id = message.get("file_id", "")
        text = message.get("text", "")
        model = message.get("model")

        self.logger.log(
            "rabbitmq:metadata",
            "Processing metadata request",
            {"file_id": file_id, "text_length": len(text), "model": model},
        )

        try:
            keywords = self.metadata_service.extract_keywords(text, model)
            self._fire_and_forget(
                self.config.files_queue,
                {"action": FilesAction.UPDATE_METADATA, "file_id": file_id, "keywords": keywords},
            )
            self.logger.log(
                "rabbitmq:metadata",
                "Metadata extracted and sent",
                {"file_id": file_id, "keywords_count": len(keywords)},
            )
        except Exception as e:
            error_str = str(e)
            is_timeout = "timeout" in error_str.lower() or "timed out" in error_str.lower()
            self.logger.log(
                "rabbitmq:metadata",
                "Error extracting metadata",
                {"file_id": file_id, "error": error_str},
                hypothesis_id="E",
            )

            try:
                keywords = self.metadata_service._extract_keywords_fallback(text)
            except Exception:
                if is_timeout:
                    keywords = ["Error: Timeout"] * 10
                else:
                    short = error_str[:50] + "..." if len(error_str) > 50 else error_str
                    keywords = [f"Error: {short}"] * 10

            self._fire_and_forget(
                self.config.files_queue,
                {"action": FilesAction.UPDATE_METADATA, "file_id": file_id, "keywords": keywords},
            )
