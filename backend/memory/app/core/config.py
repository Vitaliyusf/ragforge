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

    # Consolidation and conflict policy. Comparison is always bounded: one
    # write inspects at most `memory_dedupe_candidate_limit` existing memories,
    # so write cost does not grow with the size of an owner's memory.
    memory_dedupe_candidate_limit: int = 10
    # At or above this similarity two memories in the same scope are the same
    # fact and the new one reinforces the old rather than adding a second.
    memory_duplicate_similarity_threshold: float = 0.92
    # Between the conflict and duplicate thresholds the memories are related;
    # what happens then depends on their scope and declared fact key, never on
    # similarity alone.
    memory_conflict_similarity_threshold: float = 0.75

    # Reconciliation between MongoDB and the vector index. Every run is
    # bounded and resumable rather than a global rebuild.
    memory_reconciliation_batch_limit: int = 100
    memory_reconciliation_scan_orphans: bool = True

    # Canonical embedding boundary. Memory vectors come from the production
    # embedding service over RPC; the memory service never loads a model or
    # synthesises a vector of its own.
    embedding_queue: str = "embedding"
    memory_embedding_model: str = "intfloat/multilingual-e5-small"
    memory_embedding_dimensions: int = 384
    memory_embedding_timeout_seconds: float = 10.0
    # Bound one embedding request. Longer memory text is truncated before the
    # call so a pathological candidate cannot stall the embedding queue.
    memory_embedding_max_chars: int = 4000
    # E5/BGE retrieval models score asymmetrically; the stored memory is a
    # passage and the retrieval text is a query.
    memory_embedding_query_prefix: str = "query: "
    memory_embedding_passage_prefix: str = "passage: "

    # Memory vector index. Vector size is not configured separately: the
    # collection is created for exactly the dimensionality the canonical
    # embedding model produces.
    qdrant_enabled: bool = False
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "memory_items_v2"
    qdrant_timeout_seconds: float = 3.0
    qdrant_api_key: str = ""

    # Typed llm_agent request deadlines for chat-exit flows.
    chat_exit_llm_timeout_seconds: float = 30.0
    chat_exit_headline_timeout_seconds: float = 15.0
    chat_exit_summary_timeout_seconds: float = 20.0

    # Memory Agent bounds. Separate retry budgets make the safe failure mode
    # explicit and keep provider flakiness from expanding mutation authority.
    memory_agent_candidate_limit: int = 10
    memory_agent_history_limit: int = 24
    memory_agent_message_char_limit: int = 4000
    memory_agent_content_char_limit: int = 500
    memory_agent_structured_output_retries: int = 1
    memory_agent_business_validation_retries: int = 1
    memory_agent_tool_validation_retries: int = 0
    memory_agent_provider_retries: int = 1

    # Runtime controls
    enable_background_consumers: bool = True

# Global settings instance
settings = Settings()
