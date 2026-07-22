"""Kafka consumer used only for durable ingestion pipeline updates."""
from typing import Optional

from shared.kafka_base import BaseKafkaConsumer

from app.core.config import Settings
from app.messaging.interfaces import IConsumer


class FilesPipelineConsumer(BaseKafkaConsumer, IConsumer):
    """Consume extraction/vector stage updates from ``files.requests``."""

    def __init__(
        self,
        config: Settings,
        topic: Optional[str] = None,
        group_id: str = "files_pipeline_updates",
    ) -> None:
        super().__init__(
            config,
            topic or config.kafka_pipeline_updates_topic,
            group_id=group_id,
        )
