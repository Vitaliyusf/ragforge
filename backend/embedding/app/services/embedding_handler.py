"""Legacy embedding request handler."""
from typing import Any, Dict, List, Optional
import os
import threading
import time

import httpx

from app.core.constants import EmbeddingAction, FileStage, FileStatus
from app.core.logging_config import ServiceLogger
from app.config import EmbeddingConfig
from app.embedding.interfaces import IEmbeddingModel
from app.messaging.interfaces import IProducer
from app.services.base import BaseKafkaHandlerService
from app.utils.chunking import TextChunker
from shared.auth import attach_internal_auth_context
from shared.metrics import METRICS


class EmbeddingHandler(BaseKafkaHandlerService):
    """Process legacy embedding requests and optional file-backed vector writes.

    Accepts flat Kafka payloads, chunks text, generates embeddings, replies on
    the configured response topic, and optionally publishes legacy vector-db and
    file-stage updates for file-backed requests.
    """

    def __init__(
        self,
        producer: IProducer,
        embedding_model: Optional[IEmbeddingModel],
        logger: ServiceLogger,
        response_topic: str,
        vector_db_topic: str,
        files_topic: str,
        config: EmbeddingConfig,
    ):
        super().__init__(producer, logger, config)
        self.embedding_model = embedding_model
        self.response_topic = response_topic
        self.vector_db_topic = vector_db_topic
        self.files_topic = files_topic
        self.batch_size = config.embedding_batch_size
        self.query_prefix = getattr(config, "embedding_query_prefix", "") or ""
        self.passage_prefix = getattr(config, "embedding_passage_prefix", "") or ""
        self.metadata_fetch_timeout = getattr(config, "metadata_fetch_timeout", 5.0)
        self.chunker = TextChunker(
            strategy=config.chunking_strategy,
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )
        self._tls = threading.local()

    def process_request_with_reply(self, body: dict, reply_to: str, correlation_id: str) -> Optional[Dict[str, Any]]:
        """Handle a gateway RPC request and return the reply dict instead of sending via Kafka.

        Designed to be called from a thread executor by the RabbitMQ consumer handler.
        The return value is published back to the reply_to queue by BaseRabbitMQConsumer.

        Thread-safe: uses threading.local() to store per-call capture callbacks so that
        concurrent invocations from a thread pool never interfere with each other.
        """
        body = dict(body)  # shallow copy
        body.setdefault("reply_to", reply_to)
        body.setdefault("correlation_id", correlation_id)
        payload = body.get("payload")
        if isinstance(payload, dict):
            for key, value in payload.items():
                body.setdefault(key, value)

        _captured: Dict[str, Any] = {}

        def _capture_response(request: Dict[str, Any], data: Dict[str, Any]) -> None:
            _captured["reply"] = {"correlation_id": request.get("correlation_id"), "data": data}

        def _capture_error(request: Dict[str, Any], error_message: str) -> None:
            _captured["reply"] = {
                "correlation_id": request.get("correlation_id"),
                "data": {"embedding": [], "error": error_message},
            }

        self._tls.send_response_override = _capture_response
        self._tls.send_error_override = _capture_error
        try:
            self.process_request(body)
        finally:
            self._tls.send_response_override = None
            self._tls.send_error_override = None

        return _captured.get("reply")

    def process_request(self, request: Dict[str, Any]) -> None:
        """Handle a single legacy embedding request."""
        correlation_id = request.get("correlation_id")
        text = request.get("text", "")
        file_id = request.get("file_id")
        filename = request.get("filename", "")

        self.logger.log(
            "handler:process_embedding",
            "Processing embedding request",
            {"correlation_id": correlation_id, "text_length": len(text), "file_id": file_id, "filename": filename},
        )

        try:
            if not self.embedding_model or not self.embedding_model.is_loaded():
                self._send_error(request, "Embedding model not available")
                if file_id:
                    self._update_files_stage(file_id, FileStage.EMBEDDING, FileStatus.ERROR)
                return

            chunks = self.chunker.chunk(text)

            chunks_to_encode = chunks
            if file_id and self.passage_prefix:
                chunks_to_encode = [self.passage_prefix + c for c in chunks]
            elif not file_id and self.query_prefix:
                chunks_to_encode = [self.query_prefix + c for c in chunks]

            self.logger.log(
                "handler:process_embedding",
                "Text chunked",
                {"correlation_id": correlation_id, "num_chunks": len(chunks)},
            )

            keywords = None
            if file_id:
                keywords = self._fetch_metadata_keywords(file_id)
                level = "I" if keywords else "W"
                self.logger.log(
                    "handler:process_embedding",
                    "Metadata keywords fetched" if keywords else "Metadata keywords not available yet",
                    {"file_id": file_id, **({"keywords_count": len(keywords)} if keywords else {})},
                    hypothesis_id=level,
                )

            METRICS.embedding_requests_total.labels(
                service="embedding",
                model=self.config.model_name,
            ).inc()
            encode_started = time.monotonic()
            embeddings = self.embedding_model.encode_batch(chunks_to_encode, batch_size=self.batch_size)
            METRICS.embedding_duration.labels(service="embedding").observe(
                time.monotonic() - encode_started
            )
            first_embedding = embeddings[0] if embeddings else []

            vectors_sent = 0
            if file_id and embeddings:
                self._send_batch_to_vectordb(embeddings, chunks, file_id, filename, keywords)
                vectors_sent = len(embeddings)
                self.producer.flush()

            if file_id:
                self._update_files_stage(file_id, FileStage.EMBEDDING, FileStatus.DONE)

            self._send_response(request, {
                "embedding": first_embedding,
                "num_chunks": len(chunks),
                "vectors_sent": vectors_sent,
            })

            self.logger.log(
                "handler:process_embedding",
                "Embedding generated and sent to vectordb",
                {
                    "correlation_id": correlation_id,
                    "embedding_dim": len(first_embedding) if first_embedding else 0,
                    "num_chunks": len(chunks),
                    "file_id": file_id,
                },
            )
        except Exception as e:
            self.logger.log(
                "handler:process_embedding",
                "Error generating embedding",
                {"correlation_id": correlation_id, "error": str(e)},
                hypothesis_id="E",
            )
            if file_id:
                self._update_files_stage(file_id, FileStage.EMBEDDING, FileStatus.ERROR)
            self._send_error(request, str(e))

    def _send_response(self, request: Dict[str, Any], data: Dict[str, Any]) -> None:
        override = getattr(self._tls, "send_response_override", None)
        if override is not None:
            override(request, data)
            return
        reply_topic = request.get("reply_to") or self.response_topic
        self.producer.send(reply_topic, {"correlation_id": request.get("correlation_id"), "data": data})
        self.producer.flush()

    def _send_error(self, request: Dict[str, Any], error_message: str) -> None:
        override = getattr(self._tls, "send_error_override", None)
        if override is not None:
            override(request, error_message)
            return
        reply_topic = request.get("reply_to") or self.response_topic
        self.producer.send(reply_topic, {
            "correlation_id": request.get("correlation_id"),
            "data": {"embedding": [], "error": error_message},
        })
        self.producer.flush()

    def _send_batch_to_vectordb(
        self,
        embeddings: List[List[float]],
        chunks: List[str],
        file_id: str,
        filename: str,
        keywords: Optional[List[str]] = None,
    ) -> None:
        total_chunks = len(embeddings)
        keywords_str = ",".join(keywords) if isinstance(keywords, list) and keywords else None
        metadatas = []
        for i in range(total_chunks):
            meta = {"chunk_index": str(i), "total_chunks": str(total_chunks), "file_id": file_id}
            if filename:
                meta["filename"] = filename
            if keywords_str:
                meta["keywords"] = keywords_str
            metadatas.append(meta)

        self.producer.send(self.vector_db_topic, attach_internal_auth_context({
            "action": EmbeddingAction.BATCH_INSERT,
            "vectors": embeddings,
            "metadata": metadatas,
            "documents": chunks,
        }))
        self.logger.log(
            "handler:send_batch_to_vectordb",
            "Batch sent to vectordb",
            {"file_id": file_id, "count": total_chunks, "has_keywords": keywords is not None},
        )

    def _fetch_metadata_keywords(
        self, file_id: str, max_retries: int = 3, retry_delay: float = 1.0
    ) -> Optional[List[str]]:
        files_service_url = os.getenv("FILES_SERVICE_URL", "http://localhost:8005").rstrip("/")
        url = f"{files_service_url}/v1/files/{file_id}"

        for attempt in range(max_retries):
            try:
                auth_envelope = attach_internal_auth_context({})
                with httpx.Client(timeout=self.metadata_fetch_timeout) as client:
                    response = client.get(
                        url,
                        headers={"X-Internal-Auth": auth_envelope.get("auth_context", "")},
                    )
                    if response.status_code == 404:
                        return None
                    response.raise_for_status()
                    data = response.json()
                    keywords = data.get("metadata", {}).get("keywords")
                    return keywords if isinstance(keywords, list) else None
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                self.logger.log(
                    "handler:fetch_metadata",
                    "Error fetching metadata keywords",
                    {"file_id": file_id, "error": str(e), "attempt": attempt + 1},
                    hypothesis_id="W",
                )
                return None
        return None

    def _update_files_stage(self, file_id: str, stage: str, status: str) -> None:
        self.producer.send(self.files_topic, attach_internal_auth_context({
            "action": EmbeddingAction.UPDATE_STAGE,
            "file_id": file_id,
            "stage": stage,
            "status": status,
        }))
        self.producer.flush()
        self.logger.log(
            "handler:update_files_stage",
            "Updated file stage",
            {"file_id": file_id, "stage": stage, "status": status},
        )
