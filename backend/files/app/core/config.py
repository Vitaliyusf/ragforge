"""Configuration management using pydantic-settings."""
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Service configuration
    service_name: str = Field(default="files", description="Service name")
    service_port: int = Field(default=8005, description="Service port")
    service_host: str = Field(default="0.0.0.0", description="Service host")
    
    # Kafka configuration (embedding pipeline producer only — RPC replaced by RabbitMQ)
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers (used by embedding pipeline producer)"
    )
    kafka_pipeline_updates_topic: str = Field(
        default="files.requests",
        validation_alias=AliasChoices("FILES_PIPELINE_TOPIC", "FILES_TOPIC"),
        description="Kafka topic carrying ingestion stage updates back to files",
    )
    kafka_max_retries: int = Field(default=10, description="Kafka connection retry count")
    kafka_retry_delay: int = Field(default=2, description="Kafka retry delay in seconds")
    kafka_consumer_timeout_ms: int = Field(default=1000, description="Kafka poll timeout")
    kafka_api_version: tuple[int, int, int] = (0, 10, 1)
    files_events_topic: str = Field(
        default="files.events",
        validation_alias=AliasChoices("FILES_EVENTS_TOPIC"),
        description="Kafka topic for files domain events",
    )
    extract_topic: str = Field(
        default="embedding.requests",
        validation_alias=AliasChoices("EMBEDDING_REQUESTS_TOPIC", "EXTRACT_TOPIC"),
        description="Kafka topic used to request text extraction",
    )
    embedding_jobs_topic: str = Field(
        default="embedding.jobs.requested",
        validation_alias=AliasChoices("EMBEDDING_JOBS_TOPIC"),
        description="Kafka topic for embedding job requests",
    )
    vector_db_delete_topic: str = Field(
        default="vector_db.delete.requested",
        validation_alias=AliasChoices("VECTOR_DB_DELETE_TOPIC"),
        description="Kafka topic for vector cleanup requests",
    )
    generate_questions_topic: str = Field(
        default="generate_questions_requests",
        validation_alias=AliasChoices("GENERATE_QUESTIONS_TOPIC"),
        description="Kafka topic for LLM to generate suggested questions"
    )
    # RabbitMQ configuration (gateway request/reply)
    rabbitmq_url: str = Field(
        default="amqp://guest:guest@localhost:5672/",
        description="RabbitMQ connection URL"
    )
    rabbitmq_exchange: str = Field(
        default="ragapp.requests",
        description="RabbitMQ exchange name"
    )
    rabbitmq_queue: str = Field(
        default="files",
        description="RabbitMQ queue name for files service requests"
    )
    rabbitmq_prefetch_count: int = Field(
        default=1,
        description="RabbitMQ consumer prefetch count"
    )

    # MongoDB configuration
    mongodb_url: str = Field(
        default="mongodb://localhost:27017/",
        description="MongoDB connection URL"
    )
    files_db_name: str = Field(
        default="files",
        validation_alias=AliasChoices("FILES_DB_NAME"),
        description="MongoDB database name for files domain collections",
    )
    audit_db_name: str = Field(
        default="audit_trail",
        validation_alias=AliasChoices("AUDIT_DB_NAME"),
        description="MongoDB database name for audit collections",
    )
    mongodb_max_retries: int = Field(
        default=10,
        description="Maximum MongoDB connection retries"
    )
    mongodb_retry_delay: int = Field(
        default=2,
        description="MongoDB retry delay in seconds"
    )
    db_type: str = Field(
        default="mongodb",
        description="Database type"
    )
    
    # File storage configuration
    upload_dir: str = Field(
        default="uploads",
        description="Directory for file uploads"
    )
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, validation_alias=AliasChoices("MAX_UPLOAD_BYTES"))
    review_snippet_max_chars: int = Field(
        default=280,
        validation_alias=AliasChoices("REVIEW_SNIPPET_MAX_CHARS"),
        description="Maximum characters stored in problematic text snippets",
    )
    chunk_preview_max_chars: int = Field(
        default=120,
        validation_alias=AliasChoices("CHUNK_PREVIEW_MAX_CHARS"),
        description="Maximum characters stored in chunk preview fields",
    )
    chunk_size: int = Field(
        default=1200,
        validation_alias=AliasChoices("CHUNK_SIZE"),
        description="Chunk size used for text chunking",
    )
    chunk_overlap: int = Field(
        default=200,
        validation_alias=AliasChoices("CHUNK_OVERLAP"),
        description="Chunk overlap used for text chunking",
    )
    review_resume_token_ttl_seconds: int = Field(
        default=3600,
        validation_alias=AliasChoices("REVIEW_RESUME_TOKEN_TTL_SECONDS"),
        description="Lifetime for one-time review resume tokens",
    )
    prompt_injection_threshold: float = Field(
        default=0.8,
        validation_alias=AliasChoices("PROMPT_INJECTION_THRESHOLD"),
        description="Threshold for prompt injection review detection",
    )
    pii_high_risk_threshold: float = Field(
        default=0.8,
        validation_alias=AliasChoices("PII_HIGH_RISK_THRESHOLD"),
        description="Threshold for high-risk PII review detection",
    )
    unsafe_content_threshold: float = Field(
        default=0.8,
        validation_alias=AliasChoices("UNSAFE_CONTENT_THRESHOLD"),
        description="Threshold for unsafe/prohibited content review detection",
    )
    parser_problem_threshold: float = Field(
        default=0.7,
        validation_alias=AliasChoices("PARSER_PROBLEM_THRESHOLD"),
        description="Threshold for parser or format problems",
    )
    langsmith_tracing_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("LANGSMITH_TRACING_ENABLED"),
        description="Whether LangSmith tracing is enabled",
    )
    langsmith_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LANGSMITH_API_KEY"),
        description="LangSmith API key",
    )
    langsmith_project: str = Field(
        default="files",
        validation_alias=AliasChoices("LANGSMITH_PROJECT"),
        description="LangSmith project name",
    )
    
    class Config:
        """Pydantic config."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
