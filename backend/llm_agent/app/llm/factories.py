"""Factory for creating LLM clients."""
from typing import Optional

from app.llm.interfaces import ILLMClient
from app.llm.implementations.ollama import OllamaClient
from app.llm.implementations.queued_llm import QueuedLLMClient
from app.llm.implementations.huggingface import HuggingFaceClient
from app.llm.implementations.vllm import VLLMClient
from app.core.config import Settings
from app.core.constants import LLMImplementation


class LLMClientFactory:
    """Factory for creating LLM client instances."""
    
    @staticmethod
    def create(config: Settings, implementation: str = "ollama") -> Optional[ILLMClient]:
        """
        Create an LLM client instance.
        
        Args:
            config: Service configuration
            implementation: Implementation type ("ollama", "huggingface", "vllm", etc.)
            
        Returns:
            LLM client instance
        """
        if implementation == LLMImplementation.HUGGINGFACE:
            # Hugging Face client supports concurrent requests natively
            return HuggingFaceClient(config)
        elif implementation == LLMImplementation.VLLM:
            # vLLM client supports high-performance concurrent requests
            return VLLMClient(config)
        elif implementation == LLMImplementation.OLLAMA:
            # Ollama requires queued processing for sequential requests
            base_client = OllamaClient(config)
            return QueuedLLMClient(base_client)
        else:
            raise ValueError(f"Unknown LLM implementation: {implementation}")
