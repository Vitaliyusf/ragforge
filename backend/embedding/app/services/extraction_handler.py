"""Legacy extraction request handler."""
from typing import Any, Dict, List, Optional
import os
import time
import uuid

from app.core.constants import EmbeddingAction, FileStage, FileStatus
from shared.logging import ServiceLogger
from app.config import EmbeddingConfig
from app.extraction.interfaces import IFileExtractor
from app.extraction.factories import FileExtractorFactory
from app.messaging.interfaces import IProducer
from app.services.base import BaseKafkaHandlerService
from shared.auth import attach_internal_auth_context


class ExtractionHandler(BaseKafkaHandlerService):
    """Process legacy extraction requests and fan extracted text downstream.

    Accepts flat extraction payloads, chooses an extractor based on the file
    extension, updates the files service stage, and republishes the extracted
    text to the legacy embedding, summary, and metadata topics.
    """

    def __init__(
        self,
        producer: IProducer,
        extractors: List[IFileExtractor],
        logger: ServiceLogger,
        files_topic: str,
        summary_topic: str,
        metadata_topic: str,
        embedding_topic: str,
        config: Optional[EmbeddingConfig] = None,
        rpc_producer: Optional[IProducer] = None,
    ):
        super().__init__(producer, logger, config or EmbeddingConfig())
        self.extractors = extractors
        self.files_topic = files_topic
        self.summary_topic = summary_topic
        self.metadata_topic = metadata_topic
        self.embedding_topic = embedding_topic
        self.rpc_producer = rpc_producer or producer

    def process_request(self, request: Dict[str, Any]) -> None:
        """Handle a single legacy file extraction request."""
        normalized = self._normalize_request(request)
        file_id = normalized.get("file_id")
        file_path = normalized.get("path")
        filename = normalized.get("filename", "unknown")

        self.logger.log(
            "handler:process_extraction",
            "Processing extraction request",
            {"file_id": file_id, "filename": filename, "path": file_path},
        )

        try:
            extractor = self._get_extractor(filename)
            if not extractor:
                raise ValueError(f"Unsupported file type: {os.path.splitext(filename)[1]}")

            extraction_result = self._extract_text(extractor, file_path, filename)
            extracted_text = extraction_result["text"]
            diagnostics = extraction_result["diagnostics"]

            self.logger.log(
                "handler:process_extraction",
                "Text extracted successfully",
                {"file_id": file_id, "text_length": len(extracted_text)},
            )

            self._send_complete_extraction(normalized, extracted_text, diagnostics)

            self.rpc_producer.send(self.summary_topic, {"file_id": file_id, "text": extracted_text, "prompt": "TL;DR"})
            self.rpc_producer.flush()

            self.rpc_producer.send(self.metadata_topic, {"file_id": file_id, "text": extracted_text})
            self.rpc_producer.flush()

            self.logger.log(
                "handler:process_extraction",
                "Text sent to files completion, summary and metadata topics",
                {
                    "file_id": file_id,
                    "files_topic": self.files_topic,
                    "summary_topic": self.summary_topic,
                    "metadata_topic": self.metadata_topic,
                },
            )

        except Exception as e:
            self.logger.log(
                "handler:process_extraction",
                "Error extracting text",
                {"file_id": file_id, "error": str(e)},
                hypothesis_id="E",
            )
            self._update_stage(file_id, FileStage.EXTRACTION, FileStatus.ERROR)

    def _normalize_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(request)
        payload = request.get("payload")
        if isinstance(payload, dict):
            for key, value in payload.items():
                normalized.setdefault(key, value)
        return normalized

    def _get_extractor(self, filename: str) -> Optional[IFileExtractor]:
        return FileExtractorFactory.get_extractor_for_file(self.extractors, filename)

    def _extract_text(
        self,
        extractor: IFileExtractor,
        file_path: Optional[str],
        filename: str,
    ) -> Dict[str, Any]:
        if file_path and os.path.exists(file_path):
            return {
                "text": extractor.extract(file_path, filename),
                "diagnostics": {"source": "path", "path": file_path},
            }
        raise FileNotFoundError(f"File not found at path for {filename}: {file_path}")

    def _send_complete_extraction(
        self,
        request: Dict[str, Any],
        extracted_text: str,
        diagnostics: Dict[str, Any],
    ) -> None:
        request_id = request.get("request_id") or request.get("correlation_id") or uuid.uuid4().hex
        trace_id = request.get("trace_id") or request_id
        correlation_id = request.get("correlation_id") or request_id
        self.producer.send(
            self.files_topic,
            attach_internal_auth_context({
                "message_id": uuid.uuid4().hex,
                "message_type": "command",
                "action": EmbeddingAction.COMPLETE_EXTRACTION,
                "source_service": "embedding",
                "target_service": "files",
                "request_id": request_id,
                "trace_id": trace_id,
                "correlation_id": correlation_id,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "file_id": request.get("file_id"),
                    "document_id": request.get("document_id") or request.get("file_id"),
                    "task_id": request.get("task_id"),
                    "extracted_text": extracted_text,
                    "diagnostics": diagnostics,
                },
            }),
        )
        self.producer.flush()

    def _update_stage(self, file_id: str, stage: str, status: str) -> None:
        self.producer.send(self.files_topic, attach_internal_auth_context({
            "action": EmbeddingAction.UPDATE_STAGE,
            "file_id": file_id,
            "stage": stage,
            "status": status,
        }))
        self.producer.flush()
