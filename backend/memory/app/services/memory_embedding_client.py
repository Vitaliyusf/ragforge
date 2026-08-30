"""Canonical embedding boundary for memory vectors.

Memory has exactly one source of vectors: the production embedding service,
reached over the same RabbitMQ RPC the RAG conversation graph uses. There is
deliberately no local model, no hashing trick, and no fallback vector — a
failed embedding is an error the caller must handle, because a memory indexed
with a non-semantic vector is worse than a memory that is not indexed at all.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.config import settings
from shared.auth import verify_internal_ticket_from_envelope
from shared.logging import ServiceLogger
from shared.rabbitmq_rpc import MultiplexedRabbitMQRPCClient


class MemoryEmbeddingError(RuntimeError):
    """The embedding service did not return a usable memory vector."""


class MemoryEmbeddingClient:
    """Embed memory text through the canonical embedding service."""

    def __init__(
        self,
        logger: ServiceLogger,
        rpc_client: Optional[MultiplexedRabbitMQRPCClient] = None,
    ) -> None:
        self.logger = logger
        self._rpc_client = rpc_client

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        """Return the embedding model memory vectors are attributed to."""
        return settings.memory_embedding_model

    @property
    def dimensions(self) -> int:
        """Return the vector size the memory collection is created for."""
        return settings.memory_embedding_dimensions

    def provenance(self) -> Dict[str, Any]:
        """Return the runtime evidence describing how vectors are produced."""
        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "service": settings.embedding_queue,
            "query_prefix": settings.memory_embedding_query_prefix,
            "passage_prefix": settings.memory_embedding_passage_prefix,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_memory(self, text: str) -> List[float]:
        """Embed stored memory text as a retrieval passage."""
        return self._embed(text, settings.memory_embedding_passage_prefix)

    def embed_query(self, text: str) -> List[float]:
        """Embed retrieval text as a query."""
        return self._embed(text, settings.memory_embedding_query_prefix)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _bounded_text(self, text: str) -> str:
        """Truncate one request to the configured character budget."""
        normalized = str(text or "").strip()
        if not normalized:
            raise MemoryEmbeddingError("embedding text is empty")
        return normalized[: settings.memory_embedding_max_chars]

    def _embed(self, text: str, prefix: str) -> List[float]:
        """Run one embedding RPC and validate the returned vector."""
        payload_text = f"{prefix}{self._bounded_text(text)}"
        try:
            vector = self._request_embedding_sync(payload_text)
        except MemoryEmbeddingError:
            raise
        except Exception as exc:
            raise MemoryEmbeddingError(f"embedding request failed: {exc}") from exc

        if not isinstance(vector, list) or not vector:
            raise MemoryEmbeddingError("embedding service returned no vector")
        if len(vector) != self.dimensions:
            raise MemoryEmbeddingError(
                f"embedding dimensionality mismatch: expected {self.dimensions}, got {len(vector)}"
            )
        try:
            return [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise MemoryEmbeddingError("embedding service returned a non-numeric vector") from exc

    def _embedding_envelope(self, text: str) -> Dict[str, Any]:
        """Build one unsigned envelope; the transport adds reply/auth fields."""
        message_id = uuid4().hex
        return {
            "message_id": message_id,
            "message_type": "query",
            "action": "embed",
            "source_service": settings.service_name,
            "target_service": settings.embedding_queue,
            "request_id": message_id,
            "trace_id": message_id,
            "correlation_id": message_id,
            "timestamp": int(time.time() * 1000),
            "payload": {"action": "embed", "text": text},
        }

    def _require_rpc_client(self) -> MultiplexedRabbitMQRPCClient:
        if self._rpc_client is None:
            raise MemoryEmbeddingError("memory RPC transport is not configured")
        return self._rpc_client

    def _request_embedding_sync(self, text: str) -> List[float]:
        """Schedule one embedding RPC on the service event loop."""
        timeout = settings.memory_embedding_timeout_seconds
        try:
            reply = self._require_rpc_client().request_from_thread(
                settings.embedding_queue,
                self._embedding_envelope(text),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise MemoryEmbeddingError(
                f"embedding request timed out after {timeout:.1f}s"
            ) from exc
        return self._vector_from_reply(reply)

    def _vector_from_reply(self, reply: Optional[Dict[str, Any]]) -> List[float]:
        """Extract the vector from the embedding service reply."""
        if not isinstance(reply, dict):
            raise MemoryEmbeddingError("embedding service returned a malformed reply")
        verify_internal_ticket_from_envelope(reply, required=True)
        data: Dict[str, Any] = {}
        for key in ("data", "payload"):
            candidate = reply.get(key)
            if isinstance(candidate, dict):
                data = candidate
                break
        error = data.get("error")
        if error:
            raise MemoryEmbeddingError(str(error))
        embedding = data.get("embedding")
        return list(embedding) if isinstance(embedding, list) else []
