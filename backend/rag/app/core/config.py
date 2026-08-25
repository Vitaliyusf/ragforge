"""Configuration management for the RAG service."""
from pydantic_settings import BaseSettings


class RAGConfig(BaseSettings):
    """Configuration class for the `rag` service."""

    # Service configuration
    service_name: str = "rag"
    service_port: int = 8004
    service_host: str = "0.0.0.0"

    # RabbitMQ configuration (inbound and downstream RPC transport)
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "ragapp.requests"
    rabbitmq_queue: str = "rag"
    rabbitmq_prefetch_count: int = 1

    # Direct-exchange routing keys for downstream service calls.
    memory_routing_key: str = "memory"
    llm_agent_routing_key: str = "llm_agent"
    vector_db_routing_key: str = "vector_db"
    embedding_routing_key: str = "embedding"

    # Mongo persistence
    conversation_store_type: str = "mongodb"
    mongodb_url: str = "mongodb://localhost:27017/"
    mongodb_database: str = "rag"
    mongodb_max_retries: int = 10
    mongodb_retry_delay: int = 2

    # CORS configuration
    frontend_url: str = "http://localhost:3000"
    internal_auth_secret: str = "development-only-internal-auth-secret-change-me"
    socket_connection_ttl_seconds: int = 28_800

    # Runtime configuration
    internal_request_timeout: float = 75.0
    generation_request_timeout: float = 120.0
    evaluation_request_timeout: float = 75.0
    top_k_documents: int = 6
    max_recent_messages: int = 6
    max_memory_hits: int = 6
    min_similarity_threshold: float = 0.4
    pass_two_chunk_threshold: int = 3
    pass_two_score_threshold: float = 0.55
    debug_payload_max_chars: int = 2000
    debug_payload_max_items: int = 12
    feedback_memory_threshold: int = 3

    # Guardrail / UX behavior
    enable_retrieval_bypass: bool = True
    retrieval_bypass_max_length: int = 20
    enable_langsmith_tracing: bool = True
    langsmith_project: str = "rag"
    allow_debug_payloads: bool = True
    stream_poll_interval_seconds: float = 0.1
    stream_idle_timeout_seconds: float = 5.0
    stream_drain_timeout_seconds: float = 1.0

    # Legacy fields retained for compatibility with the current codebase/tests.
    vector_store_type: str = "in_memory"
    reranker_topic: str = "reranker_requests"
    reranker_enabled: bool = True
    reranker_top_k: int = 5
    hybrid_search_enabled: bool = True
    hybrid_search_alpha: float = 0.55

    # Collection names
    conversation_threads_collection: str = "conversation_threads"
    conversation_turns_collection: str = "conversation_turns"
    conversation_summaries_collection: str = "conversation_summaries"
    graph_checkpoints_collection: str = "graph_checkpoints"
    answer_reviews_collection: str = "answer_reviews"
    user_feedback_collection: str = "user_feedback"
    flow_feedback_collection: str = "flow_feedback"
    metrics_turn_facts_collection: str = "metrics_turn_facts"

    # Admin metrics retention
    metrics_retention_days: int = 90

    class Config:
        env_file = ".env"
        case_sensitive = False

    def validate(self) -> bool:
        """Validate configuration values."""
        if not self.rabbitmq_url:
            return False
        return True


# Convenience alias used by RabbitMQ implementation modules.
Settings = RAGConfig
