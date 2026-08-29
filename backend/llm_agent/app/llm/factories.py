"""Factory for the supported vLLM provider client."""

from app.llm.interfaces import ILLMClient
from app.llm.implementations.vllm import VLLMClient
from app.core.config import Settings
from app.core.constants import LLMImplementation


class LLMClientFactory:
    """Factory for creating LLM client instances."""
    
    @staticmethod
    def create(config: Settings, implementation: str = "vllm") -> ILLMClient:
        """Create the sole production provider, rejecting stale configuration."""
        if implementation != LLMImplementation.VLLM:
            raise ValueError(f"Unknown LLM implementation: {implementation}")
        return VLLMClient(config)
