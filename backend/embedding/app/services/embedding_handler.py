"""Canonical query-embedding boundary for retrieval RPC calls."""
from typing import Any, Dict, Optional
import time

from app.config import EmbeddingConfig
from app.services.inference_scheduler import (
    CLASS_BACKGROUND,
    CLASS_LIVE,
    EmbeddingScheduler,
    EmbeddingSchedulerOverloaded,
    EmbeddingSchedulerUnavailable,
)
from shared.logging import ServiceLogger
from shared.metrics import METRICS, TRAFFIC_CLASS_EVAL, traffic_class


class QueryEmbeddingHandler:
    """Embed exactly one retrieval query and return a RabbitMQ reply payload."""

    def __init__(
        self,
        scheduler: EmbeddingScheduler,
        logger: ServiceLogger,
        config: EmbeddingConfig,
    ) -> None:
        # The handler never touches the model: the process-level scheduler owns
        # every forward pass, so two concurrent queries can share one batch.
        self.scheduler = scheduler
        self.logger = logger
        self.config = config
        self.query_prefix = config.embedding_query_prefix or ""

    def process_request_with_reply(
        self,
        body: Dict[str, Any],
        reply_to: str,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """Process one typed ``embed`` query without passage chunking or writes."""
        del reply_to  # BaseRabbitMQConsumer owns reply routing.
        payload = body.get("payload")
        request = payload if isinstance(payload, dict) else body
        text = request.get("text", "")
        request_correlation_id = body.get("correlation_id") or correlation_id

        if not isinstance(text, str):
            return self._reply(request_correlation_id, error="text must be a string")
        if body.get("action") not in (None, "embed"):
            return self._reply(request_correlation_id, error="unsupported embedding action")
        if not self.scheduler.is_available():
            return self._reply(request_correlation_id, error="Embedding model not available")

        self.logger.log(
            "query_embedding:process",
            "Processing query embedding",
            {"correlation_id": request_correlation_id, "text_length": len(text)},
        )
        try:
            METRICS.embedding_requests_total.labels(
                service="embedding",
                model=self.config.model_name,
                traffic_class=traffic_class(),
            ).inc()
            started = time.monotonic()
            embedding = self.scheduler.encode_one(
                f"{self.query_prefix}{text}",
                scheduling_class=self._scheduling_class(),
            )
            METRICS.embedding_duration.labels(
                service="embedding",
                traffic_class=traffic_class(),
            ).observe(time.monotonic() - started)
            return self._reply(request_correlation_id, embedding=embedding)
        except EmbeddingSchedulerOverloaded:
            # Deliberately not converted into a reply payload: the RabbitMQ
            # boundary translates this type into the typed `service_overloaded`
            # busy reply the gateway already understands.
            self.logger.log(
                "query_embedding:process",
                "Query embedding rejected by inference backpressure",
                {"correlation_id": request_correlation_id},
                hypothesis_id="W",
            )
            raise
        except EmbeddingSchedulerUnavailable:
            return self._reply(request_correlation_id, error="Embedding model not available")
        except Exception as exc:
            self.logger.log(
                "query_embedding:process",
                "Query embedding failed",
                {
                    "correlation_id": request_correlation_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                hypothesis_id="E",
            )
            return self._reply(request_correlation_id, error=str(exc))

    @staticmethod
    def _scheduling_class() -> str:
        """Eval traffic is scheduled as background so it never precedes a query."""
        return CLASS_BACKGROUND if traffic_class() == TRAFFIC_CLASS_EVAL else CLASS_LIVE

    @staticmethod
    def _reply(
        correlation_id: str,
        *,
        embedding: Optional[list[float]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {"embedding": embedding or []}
        if error is not None:
            data["error"] = error
        return {"correlation_id": correlation_id, "data": data}
