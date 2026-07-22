"""Consumer worker that wraps EmbeddingJobService with Kafka offset commits."""
from typing import Any, Dict

from app.services.embedding_job_service import EmbeddingJobService
from app.core.logging_config import ServiceLogger
from app.messaging.embedding_kafka import EmbeddingKafkaConsumer


class EmbeddingJobConsumerWorker:
    """Wrap typed embedding-job processing with manual Kafka commits."""

    def __init__(
        self,
        consumer: EmbeddingKafkaConsumer,
        job_service: EmbeddingJobService,
        logger: ServiceLogger,
    ) -> None:
        self.consumer = consumer
        self.job_service = job_service
        self.logger = logger

    def handle_message(self, message: Dict[str, Any]) -> bool:
        """Process a typed embedding-job message and commit when safe.

        Returns True when the message was processed or terminally handled
        and the consumer offset was committed.
        """
        should_commit = self.job_service.process_message(message)
        if should_commit:
            self.consumer.commit()
            self.logger.log(
                "embedding_job:commit",
                "Committed embedding job offset",
                {
                    "message_id": message.get("message_id"),
                    "request_id": message.get("request_id"),
                },
            )
        return should_commit
