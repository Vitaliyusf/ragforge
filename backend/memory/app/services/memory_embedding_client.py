"""Canonical embedding boundary for memory vectors.

Memory has exactly one source of vectors: the production embedding service,
reached over the same RabbitMQ RPC the RAG conversation graph uses. There is
deliberately no local model, no hashing trick, and no fallback vector — a
failed embedding is an error the caller must handle, because a memory indexed
with a non-semantic vector is worse than a memory that is not indexed at all.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aio_pika

from app.core.config import settings
from shared.auth import attach_internal_auth_context, verify_internal_ticket_from_envelope
from shared.logging import ServiceLogger


class MemoryEmbeddingError(RuntimeError):
    """The embedding service did not return a usable memory vector."""


class MemoryEmbeddingClient:
    """Embed memory text through the canonical embedding service."""

    def __init__(self, logger: ServiceLogger) -> None:
        self.logger = logger

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
            vector = asyncio.run(self._request_embedding(payload_text))
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

    async def _request_embedding(self, text: str) -> List[float]:
        """Publish one ``embed`` request and await its reply."""
        timeout = settings.memory_embedding_timeout_seconds
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        try:
            async with connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    settings.rabbitmq_exchange,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True,
                )
                reply_queue = await channel.declare_queue(exclusive=True, auto_delete=True)
                message_id = uuid4().hex
                envelope = attach_internal_auth_context(
                    {
                        "message_id": message_id,
                        "message_type": "query",
                        "action": "embed",
                        "source_service": settings.service_name,
                        "target_service": settings.embedding_queue,
                        "request_id": message_id,
                        "trace_id": message_id,
                        "correlation_id": message_id,
                        "reply_to": reply_queue.name,
                        "timestamp": int(time.time() * 1000),
                        "payload": {"action": "embed", "text": text},
                    }
                )
                await exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(envelope).encode("utf-8"),
                        correlation_id=message_id,
                        reply_to=reply_queue.name,
                        content_type="application/json",
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=settings.embedding_queue,
                )
                try:
                    async with asyncio.timeout(timeout):
                        async with reply_queue.iterator() as iterator:
                            async for message in iterator:
                                async with message.process():
                                    if message.correlation_id and message.correlation_id != message_id:
                                        continue
                                    return self._vector_from_reply(json.loads(message.body))
                except TimeoutError as exc:
                    raise MemoryEmbeddingError(
                        f"embedding request timed out after {timeout:.1f}s"
                    ) from exc
        finally:
            await connection.close()
        raise MemoryEmbeddingError("embedding reply queue closed before a response arrived")

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
