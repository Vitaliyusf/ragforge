"""Read-only access to the effective LLM service configuration."""
from typing import Any, Dict, Optional

from app.core.config import Settings, get_settings
from app.core.logging_config import ServiceLogger


class ConfigService:
    """Expose startup-effective settings without pretending to mutate them."""

    def __init__(
        self,
        logger: ServiceLogger,
        config: Optional[Settings] = None,
    ) -> None:
        self.logger = logger
        self.config = config or get_settings()

    def get_config(self) -> Dict[str, Any]:
        """Return non-secret configuration captured at service startup."""
        return {
            "configuration_policy": {
                "owner": "deployment",
                "live_effective": [],
                "restart_required": [
                    "llm_implementation",
                    "device",
                    "max_concurrent_requests",
                    "models",
                    "generation_params",
                    "vllm",
                    "ollama_url",
                    "timeouts",
                ],
            },
            "llm_implementation": self.config.llm_implementation,
            "device": self.config.device,
            "max_concurrent_requests": self.config.max_concurrent_requests,
            "ollama_url": self.config.ollama_url,
            "models": {
                "summary": self.config.summary_model,
                "metadata": self.config.metadata_model,
                "rag_chat": self.config.rag_chat_model,
                "default": self.config.default_model,
            },
            "generation_params": {
                "huggingface": {
                    "max_length": self.config.hf_max_length,
                    "temperature": self.config.hf_temperature,
                    "top_p": self.config.hf_top_p,
                    "do_sample": self.config.hf_do_sample,
                },
                "vllm": {
                    "max_tokens": self.config.vllm_max_tokens,
                    "temperature": self.config.vllm_temperature,
                    "top_p": self.config.vllm_top_p,
                    "top_k": self.config.vllm_top_k,
                },
            },
            "vllm": {
                "base_url": self.config.vllm_base_url,
                "max_model_len": self.config.vllm_max_model_len,
            },
            "timeouts": {
                "llm": self.config.llm_timeout,
                "summary": self.config.summary_timeout,
                "metadata": self.config.metadata_timeout,
            },
        }
