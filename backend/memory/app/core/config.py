"""Configuration management using pydantic-settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Service configuration
    service_name: str = "memory"
    service_port: int = 8007
    service_host: str = "0.0.0.0"

    # RabbitMQ configuration
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "ragapp.requests"
    rabbitmq_queue: str = "memory"
    # Process several requests concurrently so fast CRUD (get_messages/get_chats)
    # is never stuck behind a slow LLM-backed job on this same queue — chat-exit
    # curation/summarisation can take ~20s and would otherwise stall history
    # loads with prefetch_count=1. Dependent writes are ordered by the caller,
    # which awaits each add_message before sending the next.
    rabbitmq_prefetch_count: int = 10
    llm_agent_queue: str = "llm_agent"

    # MongoDB configuration
    mongodb_url: str = "mongodb://localhost:27017/"
    mongodb_database: str = "chats"
    mongodb_max_retries: int = 10
    mongodb_retry_delay: int = 2

    # Memory retrieval configuration
    memory_retrieval_default_limit: int = 6

    # Optional Qdrant configuration
    qdrant_enabled: bool = False
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "memory_items_v1"
    qdrant_vector_size: int = 128
    qdrant_timeout_seconds: float = 3.0
    qdrant_api_key: str = ""

    # Typed llm_agent request deadlines for chat-exit flows.
    chat_exit_llm_timeout_seconds: float = 30.0
    chat_exit_headline_timeout_seconds: float = 15.0
    chat_exit_summary_timeout_seconds: float = 20.0

    # Runtime controls
    enable_background_consumers: bool = True

# Global settings instance
settings = Settings()
