"""Configuration management using Pydantic BaseSettings."""
import logging
import os
import json
from typing import ClassVar, Dict, Optional
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Configuration class for llm_agent service using Pydantic BaseSettings."""

    _ACTION_MAX_TOKEN_FIELDS: ClassVar[Dict[str, str]] = {
        "answer_generation": "answer_generation_max_tokens",
        "answer_evaluation": "answer_evaluation_max_tokens",
        "content_risk_scan": "content_risk_scan_max_tokens",
        "query_rewrite": "query_rewrite_max_tokens",
        "memory_extraction": "memory_extraction_max_tokens",
    }
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )
    
    # Service configuration
    service_name: str = Field(default="llm_agent", description="Service name")
    service_port: int = Field(default=8001, description="Service port")
    service_host: str = Field(default="0.0.0.0", description="Service host")
    
    # RabbitMQ configuration
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/")
    rabbitmq_exchange: str = Field(default="ragapp.requests")
    rabbitmq_queue: str = Field(default="llm_agent")
    rabbitmq_prefetch_count: int = Field(default=1)
    llm_request_prefetch: int = Field(
        default=4,
        ge=1,
        le=4,
        description="Prefetch for the primary typed LLM request queue",
    )

    # Additional queues consumed by llm_agent
    summary_queue: str = Field(default="summary")
    metadata_queue: str = Field(default="metadata")
    generate_questions_queue: str = Field(default="generate_questions")
    model_queue: str = Field(default="models")
    model_management_queue: str = Field(default="model_management")
    config_management_queue: str = Field(default="config_management")

    # Files routing key (used by fire-and-forget pipeline handlers)
    files_queue: str = Field(default="files")
    
    # LLM configuration
    llm_implementation: str = Field(default="huggingface", description="LLM implementation (huggingface, vllm, ollama)")

    # Answer citations change user-visible answer text (inline [1] markers),
    # so the behaviour is switchable without a rollback.
    enable_answer_citations: bool = Field(
        default=True,
        description="Ask the model for inline [n] citations and extract them into citations[]",
    )
    
    # Model configuration
    summary_model: str = Field(default="RedHatAI/Qwen3.5-4B-quantized.w4a16", description="Summary model")
    metadata_model: str = Field(default="RedHatAI/Qwen3.5-4B-quantized.w4a16", description="Metadata extraction model")
    rag_chat_model: str = Field(default="RedHatAI/Qwen3.5-4B-quantized.w4a16", description="RAG chat model")
    default_model: Optional[str] = Field(default=None, description="Default model (falls back to rag_chat_model)")
    
    # Device configuration
    device: str = Field(default="auto", description="Device (auto, cuda, cpu, mps)")
    max_concurrent_requests: int = Field(default=10, description="Max concurrent requests")
    
    # Hugging Face generation parameters
    hf_max_length: int = Field(default=512, description="HF max generation length")
    hf_temperature: float = Field(default=0.7, description="HF temperature")
    hf_top_p: float = Field(default=0.9, description="HF top-p")
    hf_do_sample: bool = Field(default=True, description="HF do sample")
    
    # vLLM generation parameters
    vllm_max_tokens: int = Field(
        default=512,
        ge=1,
        description="Fallback output-token budget for legacy and unknown LLM actions",
    )
    answer_generation_max_tokens: int = Field(default=128, ge=1, le=131072)
    answer_evaluation_max_tokens: int = Field(default=512, ge=1, le=131072)
    content_risk_scan_max_tokens: int = Field(default=128, ge=1, le=131072)
    query_rewrite_max_tokens: int = Field(default=128, ge=1, le=131072)
    memory_extraction_max_tokens: int = Field(default=512, ge=1, le=131072)
    # Summaries need far more room than the chat default: a truncation at 512
    # tokens cuts a document summary off mid-sentence (and non-Latin scripts such
    # as Hebrew burn ~2 tokens/char, so 512 tokens is only ~1k characters).
    summary_max_tokens: int = Field(default=2048, description="Max output tokens for summarization")
    vllm_temperature: float = Field(default=0.7, description="vLLM temperature")
    vllm_top_p: float = Field(default=0.9, description="vLLM top-p")
    vllm_top_k: int = Field(default=50, description="vLLM top-k")
    vllm_max_model_len: int = Field(
        default=6144,
        description="Fallback context window in tokens; keep in sync with the vLLM --max-model-len arg",
    )
    vllm_base_url: str = Field(default="http://localhost:8000", description="vLLM base URL")
    vllm_api_key: str = Field(default="none", description="vLLM bearer API key")
    
    # Legacy Ollama configuration
    ollama_url: str = Field(default="http://host.docker.internal:11434", description="Ollama URL")
    
    # Model cache configuration
    models_cache_ttl: int = Field(default=300, description="Models cache TTL in seconds")
    models_cache_implementation: str = Field(default="memory", description="Models cache implementation")
    
    # Model preloading configuration
    preload_models: bool = Field(default=True, description="Preload models")
    preload_models_on_startup: bool = Field(default=True, description="Preload models on startup")
    
    # Timeout configuration
    llm_timeout: float = Field(default=60.0, description="LLM timeout in seconds")
    summary_timeout: float = Field(default=120.0, description="Summary timeout in seconds")
    metadata_timeout: float = Field(default=60.0, description="Metadata timeout in seconds")
    
    # Text processing configuration
    debug_max_field_length: int = Field(default=8000, description="Max debug payload length per field")

    # LangSmith tracing configuration
    langsmith_enabled: bool = Field(default=False, description="Enable LangSmith tracing")
    langsmith_api_key: Optional[str] = Field(default=None, description="LangSmith API key")
    langsmith_project: str = Field(default="llm_agent", description="LangSmith project name")
    langsmith_endpoint: Optional[str] = Field(default=None, description="LangSmith API endpoint")
    
    # MongoDB configuration
    mongodb_url: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URL")
    mongodb_database: str = Field(default="llm_agent", description="MongoDB database name")
    
    def __init__(self, **kwargs):
        """Initialize settings with config file support."""
        # Load config from file first (if exists)
        config_file = Path(os.getenv("CONFIG_FILE", "/app/config.json"))
        file_config = {}
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    file_config = json.load(f)
            except Exception as e:
                logger.warning("Failed to load config from %s: %s", config_file, e)
        else:
            # Try to load from logs
            try:
                log_dir = os.getenv("LOG_DIR", os.path.join(Path(__file__).parent.parent.parent, "logs"))
                log_path = os.path.join(log_dir, "llm_agent_service.log")
                
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    for line in reversed(lines):
                        try:
                            log_entry = json.loads(line.strip())
                            if (log_entry.get("location") == "handler:config_management" and 
                                "Configuration saved to file and logged" in log_entry.get("message", "")):
                                full_config = log_entry.get("data", {}).get("full_config_state")
                                if full_config:
                                    file_config = full_config
                                    break
                        except (json.JSONDecodeError, KeyError):
                            continue
            except Exception as e:
                logger.warning("Failed to load config from logs: %s", e)
        
        # Merge: env vars > file config > defaults
        # First, get defaults from Pydantic
        merged = {}
        
        # Apply file config
        for key, value in file_config.items():
            # Convert to field name (snake_case)
            field_name = key
            merged[field_name] = value
        
        # Apply kwargs (env vars take precedence via Pydantic)
        merged.update(kwargs)
        
        # Validate summary_model
        summary_model_val = merged.get("summary_model", file_config.get("summary_model", "RedHatAI/Qwen3.5-4B-quantized.w4a16"))
        if self._is_mbart_model(summary_model_val):
            logger.error("Model %s is a translation model (mbart), not suitable for summarization. Correcting to: RedHatAI/Qwen3.5-4B-quantized.w4a16", summary_model_val)
            merged["summary_model"] = "RedHatAI/Qwen3.5-4B-quantized.w4a16"
            summary_model_val = "RedHatAI/Qwen3.5-4B-quantized.w4a16"
        
        # Set default_model if not provided
        if not merged.get("default_model") and not file_config.get("default_model"):
            merged["default_model"] = merged.get("rag_chat_model", file_config.get("rag_chat_model", "RedHatAI/Qwen3.5-4B-quantized.w4a16"))
        
        super().__init__(**merged)
    
    @staticmethod
    def _is_mbart_model(model_name: str) -> bool:
        """Check if a model is an mbart (translation) model, not suitable for summarization."""
        if not model_name:
            return False
        return "mbart" in model_name.lower()
    
    def validate(self) -> bool:
        """Validate configuration values."""
        if not self.rabbitmq_url:
            return False
        if not self.rabbitmq_exchange or not self.rabbitmq_queue:
            return False
        return True

    @model_validator(mode="after")
    def validate_output_token_budgets(self) -> "Settings":
        """Reject output ceilings that cannot fit inside the configured window."""
        fields = (
            "vllm_max_tokens",
            "summary_max_tokens",
            *self._ACTION_MAX_TOKEN_FIELDS.values(),
        )
        for field_name in fields:
            if getattr(self, field_name) > self.vllm_max_model_len:
                raise ValueError(
                    f"{field_name} must not exceed vllm_max_model_len "
                    f"({self.vllm_max_model_len})"
                )
        return self

    def max_tokens_for_request_type(self, request_type: str) -> int:
        """Resolve a typed action budget, falling back for legacy/unknown callers."""
        field_name = self._ACTION_MAX_TOKEN_FIELDS.get(request_type)
        return getattr(self, field_name) if field_name else self.vllm_max_tokens


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
