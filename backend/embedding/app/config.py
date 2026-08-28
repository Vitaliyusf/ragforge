"""Configuration management for the embedding service."""
import os
from typing import Optional


class EmbeddingConfig:
    """Configuration class for embedding service."""
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        # Service configuration
        self.service_name: str = os.getenv("SERVICE_NAME", "embedding")
        self.service_port: int = int(os.getenv("SERVICE_PORT", "8002"))
        self.service_host: str = os.getenv("SERVICE_HOST", "0.0.0.0")
        
        # Kafka configuration
        self.kafka_bootstrap_servers: str = os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", 
            "localhost:9092"
        )
        self.extract_topic: str = os.getenv("EXTRACT_TOPIC", "embedding.requests")
        self.summary_topic: str = os.getenv("SUMMARY_TOPIC", "summary")
        self.metadata_topic: str = os.getenv("METADATA_TOPIC", "metadata")
        self.files_topic: str = os.getenv("FILES_TOPIC", "files.requests")
        self.embedding_jobs_requested_topic: str = os.getenv(
            "EMBEDDING_JOBS_REQUESTED_TOPIC",
            "embedding.jobs.requested"
        )
        self.vector_db_upsert_requested_topic: str = os.getenv(
            "VECTOR_DB_UPSERT_REQUESTED_TOPIC",
            "vector_db.upsert.requested"
        )
        self.embedding_jobs_completed_topic: str = os.getenv(
            "EMBEDDING_JOBS_COMPLETED_TOPIC",
            "embedding.jobs.completed"
        )
        self.embedding_consumer_group: str = os.getenv(
            "EMBEDDING_CONSUMER_GROUP",
            f"{self.service_name}_embedding_jobs_consumer"
        )
        self.kafka_max_retries: int = int(os.getenv("KAFKA_MAX_RETRIES", "10"))
        self.kafka_retry_delay: int = int(os.getenv("KAFKA_RETRY_DELAY", "2"))
        self.kafka_consumer_timeout_ms: int = int(os.getenv("KAFKA_CONSUMER_TIMEOUT_MS", "1000"))
        self.kafka_api_version: tuple = (0, 10, 1)

        # RabbitMQ configuration (gateway request queue)
        self.rabbitmq_url: str = os.getenv(
            "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        )
        self.rabbitmq_exchange: str = os.getenv("RABBITMQ_EXCHANGE", "ragapp.requests")
        self.rabbitmq_queue: str = os.getenv("RABBITMQ_QUEUE", "embedding")
        self.rabbitmq_prefetch_count: int = int(os.getenv("RABBITMQ_PREFETCH_COUNT", "1"))

        # Model configuration
        # Default: multilingual-e5-small (512 tokens, retrieval-optimized, 384 dims)
        self.model_name: str = os.getenv(
            "EMBEDDING_MODEL", 
            "intfloat/multilingual-e5-small"
        )
        self.model_type: str = os.getenv("EMBEDDING_MODEL_TYPE", "auto")  # auto, sentence_transformers
        self.embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
        self.embedding_max_batch_size: int = int(
            os.getenv("EMBEDDING_MAX_BATCH_SIZE", str(self.embedding_batch_size))
        )
        self.vector_db_collection_name: str = os.getenv("VECTOR_DB_COLLECTION_NAME", "rag_chunks_v1")
        
        # E5/BGE retrieval models require query/passage prefixes for optimal retrieval
        _use_e5_prefix = "e5" in self.model_name.lower() or "bge" in self.model_name.lower()
        self.embedding_query_prefix: str = os.getenv("EMBEDDING_QUERY_PREFIX", "query: " if _use_e5_prefix else "")
        self.embedding_passage_prefix: str = os.getenv("EMBEDDING_PASSAGE_PREFIX", "passage: " if _use_e5_prefix else "")
        
        # LangSmith configuration
        self.langsmith_tracing: bool = os.getenv("LANGSMITH_TRACING", "false").lower() in ("1", "true", "yes", "on")
        self.langsmith_api_key: Optional[str] = os.getenv("LANGSMITH_API_KEY")
        self.langsmith_project: Optional[str] = os.getenv("LANGSMITH_PROJECT")

        # Gateway upload extraction uses GridFS-backed file handles.
        self.mongodb_url: str = os.getenv(
            "MONGODB_URL",
            os.getenv("MONGO_CONNECTION_STRING", "mongodb://localhost:27017/"),
        )
        self.mongo_database_name: str = os.getenv("MONGO_DATABASE_NAME", "gateway")
        self.gridfs_bucket_name: str = os.getenv("GRIDFS_BUCKET_NAME", "gateway_files")


    def validate(self) -> bool:
        """Validate configuration values."""
        if not self.kafka_bootstrap_servers:
            return False
        if not self.extract_topic or not self.embedding_jobs_requested_topic:
            return False
        return True
