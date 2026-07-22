"""Configuration management using pydantic-settings."""
from pydantic_settings import BaseSettings
from typing import Tuple


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service configuration
    service_name: str = "vector_db"
    service_port: int = 8006
    service_host: str = "0.0.0.0"

    # Kafka configuration (upsert/delete pipeline — NOT for RPC)
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_upsert_requested_topic: str = "vector_db.upsert.requested"
    kafka_delete_requested_topic: str = "vector_db.delete.requested"
    kafka_upsert_completed_topic: str = "vector_db.upsert.completed"
    kafka_files_topic: str = "files.requests"
    kafka_max_retries: int = 10
    kafka_retry_delay: int = 2
    kafka_consumer_timeout_ms: int = 1000
    kafka_api_version: Tuple[int, int, int] = (0, 10, 1)

    # RabbitMQ configuration (gateway request/reply)
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "ragapp.requests"
    rabbitmq_queue: str = "vector_db"
    rabbitmq_prefetch_count: int = 1

    # Vector store backend — "qdrant" | "chromadb" | "in_memory"
    vector_store_type: str = "qdrant"

    # Qdrant configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "rag_chunks_v1"
    qdrant_vector_size: int = 384
    qdrant_api_key: str = ""
    qdrant_https: bool = False

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
    }


settings = Settings()
