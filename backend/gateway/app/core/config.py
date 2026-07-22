"""Configuration management for the gateway service."""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field, field_validator, model_validator


class GatewayConfig(BaseSettings):
    """Configuration class for gateway service using pydantic-settings."""

    # Service configuration
    service_name: str = Field(default="gateway")
    service_port: int = Field(default=8000)
    service_host: str = Field(default="0.0.0.0")
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "environment"),
    )

    # Authentication and browser boundary
    auth_required: bool = Field(default=True)
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
    )
    session_cookie_name: str = Field(default="ragapp_session")
    csrf_cookie_name: str = Field(default="ragapp_csrf")
    session_cookie_secure: bool = Field(default=False)
    session_cookie_samesite: str = Field(default="strict")
    session_cookie_domain: str = Field(default="")
    session_ttl_seconds: int = Field(default=28_800)
    internal_auth_secret: str = Field(
        default="development-only-internal-auth-secret-change-me",
    )
    internal_auth_ticket_ttl_seconds: int = Field(default=60)
    password_pepper: str = Field(default="")
    session_pepper: str = Field(default="")
    bootstrap_tenant_id: str = Field(default="default")
    bootstrap_tenant_name: str = Field(default="Default Workspace")
    bootstrap_admin_email: str = Field(default="")
    bootstrap_admin_password: str = Field(default="")
    max_upload_bytes: int = Field(default=25 * 1024 * 1024)
    allowed_upload_extensions: str = Field(default=".pdf,.txt,.md,.docx")
    allowed_upload_content_types: str = Field(
        default="application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    # RabbitMQ configuration
    rabbitmq_url: str = Field(
        default="amqp://guest:guest@localhost:5672/",
    )
    rabbitmq_exchange: str = Field(default="ragapp.requests")
    rabbitmq_prefetch_count: int = Field(default=1)

    # Routing keys (one per downstream service / handler group)
    llm_agent_routing_key: str = Field(default="llm_agent")
    embedding_routing_key: str = Field(default="embedding")
    rag_routing_key: str = Field(default="rag")
    files_routing_key: str = Field(default="files")
    vector_db_routing_key: str = Field(default="vector_db")
    memory_routing_key: str = Field(default="memory")
    model_management_routing_key: str = Field(default="model_management")
    config_management_routing_key: str = Field(default="config_management")

    # MongoDB / GridFS configuration
    mongo_connection_string: str = Field(
        default="mongodb://localhost:27017",
    )
    mongo_database_name: str = Field(default="gateway")
    gridfs_bucket_name: str = Field(default="gateway_files")

    # Request timeout configuration
    default_timeout: float = Field(default=120.0)
    short_timeout: float = Field(default=30.0)

    # Log service configuration
    log_services: str = Field(
        default="gateway,files,embedding,llm_agent,memory,rag,reranker,vector_db",
    )

    gateway_deployment_replicas: int = Field(default=1)

    # Aliases so existing service code that calls self.config.rag_topic etc. needs zero changes
    @property
    def llm_agent_topic(self) -> str:
        return self.llm_agent_routing_key

    @property
    def embedding_topic(self) -> str:
        return self.embedding_routing_key

    @property
    def rag_topic(self) -> str:
        return self.rag_routing_key

    @property
    def files_topic(self) -> str:
        return self.files_routing_key

    @property
    def vector_db_topic(self) -> str:
        return self.vector_db_routing_key

    @property
    def memory_topic(self) -> str:
        return self.memory_routing_key

    @property
    def model_management_topic(self) -> str:
        return self.model_management_routing_key

    @property
    def config_management_topic(self) -> str:
        return self.config_management_routing_key

    @property
    def models_topic(self) -> str:
        return "models"

    @property
    def request_topics(self) -> dict[str, str]:
        """Compatibility mapping backed entirely by RabbitMQ routing keys."""
        return {
            "llm_agent": self.llm_agent_routing_key,
            "embedding": self.embedding_routing_key,
            "rag": self.rag_routing_key,
            "files": self.files_routing_key,
            "vector_db": self.vector_db_routing_key,
            "memory": self.memory_routing_key,
            "models": self.models_topic,
            "model_management": self.model_management_routing_key,
            "config_management": self.config_management_routing_key,
        }

    @property
    def log_services_list(self) -> List[str]:
        return [s.strip() for s in self.log_services.split(",")]

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_upload_extensions_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_upload_extensions.split(",") if item.strip()}

    @property
    def allowed_upload_content_types_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_upload_content_types.split(",") if item.strip()}

    @field_validator("service_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("default_timeout", "short_timeout")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Timeout must be positive")
        return v

    @field_validator("session_cookie_samesite")
    @classmethod
    def validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("SESSION_COOKIE_SAMESITE must be lax, strict, or none")
        return normalized

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "GatewayConfig":
        if self.auth_required and len(self.internal_auth_secret.encode("utf-8")) < 32:
            raise ValueError("INTERNAL_AUTH_SECRET must contain at least 32 bytes")
        if self.environment.lower() in {"production", "prod"}:
            if not self.auth_required:
                raise ValueError("AUTH_REQUIRED must be true in production")
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production")
            if self.session_cookie_domain:
                raise ValueError("SESSION_COOKIE_DOMAIN must be empty for __Host- cookies")
            if not self.session_cookie_name.startswith("__Host-"):
                raise ValueError("SESSION_COOKIE_NAME must use the __Host- prefix in production")
            if not self.csrf_cookie_name.startswith("__Host-"):
                raise ValueError("CSRF_COOKIE_NAME must use the __Host- prefix in production")
            if self.session_cookie_samesite == "none":
                raise ValueError("SESSION_COOKIE_SAMESITE=none is forbidden in production")
            if "development-only" in self.internal_auth_secret:
                raise ValueError("The development internal authentication secret is forbidden in production")
            if len(self.password_pepper.encode("utf-8")) < 32:
                raise ValueError("PASSWORD_PEPPER must contain at least 32 bytes in production")
            if len(self.session_pepper.encode("utf-8")) < 32:
                raise ValueError("SESSION_PEPPER must contain at least 32 bytes in production")
            if any(origin.startswith("http://") for origin in self.cors_origins_list):
                raise ValueError("Production CORS origins must use HTTPS")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
