"""Model management service."""
import os
import threading
from typing import Dict, Any

from app.llm.interfaces import ILLMClient
from app.cache.interfaces import IModelCache
from shared.logging import ServiceLogger
from app.core.config import Settings
from app.core.constants import LLMImplementation
from app.core.errors import ServiceException, NotFoundException, ValidationException
from app.services.base import BaseService


class ModelService(BaseService):
    """Service for model management operations."""

    def __init__(
        self,
        llm_client: ILLMClient,
        model_cache: IModelCache,
        logger: ServiceLogger,
        config: Settings,
    ):
        super().__init__(llm_client, logger, config)
        self.model_cache = model_cache
        self._download_status: Dict[str, Dict] = {}
        self._download_lock = threading.Lock()
    
    def list_models(self) -> Dict[str, Any]:
        """
        List available models.
        
        Returns:
            Dictionary with models list and metadata
        """
        self.logger.log("service:model", "Listing models")
        
        try:
            # Get models from cache, refresh if needed
            if not self.model_cache.is_valid():
                # Cache expired, fetch fresh
                models = self.llm_client.list_models()
                self.model_cache.set_models(models)
                self.logger.log(
                    "service:model",
                    "Models fetched and cached",
                    {"model_count": len(models)}
                )
            
            models = self.model_cache.get_models()
            if not models:
                # Fallback to default model
                models = [self.config.default_model]
            
            # Get model information for each model
            model_info_list = []
            for model in models:
                model_name = model if isinstance(model, str) else model.get("name", str(model))
                info = self.get_model_info(model_name)
                model_info_list.append(info)
            
            return {
                "status": "success",
                "models": model_info_list,
                "count": len(models),
                "default": self.config.default_model,
                "cached": self.model_cache.is_valid(),
                "last_updated": (
                    self.model_cache.get_last_updated().isoformat()
                    if self.model_cache.get_last_updated() is not None
                    else None
                )
            }
        except Exception as e:
            self.logger.log(
                "service:model",
                "Error listing models",
                {"error": str(e)},
                hypothesis_id="E"
            )
            raise ServiceException(f"Failed to list models: {str(e)}", original_exception=e)
    
    def llm_ready(self) -> Dict[str, Any]:
        """Report whether the active LLM backend is reachable and ready to serve.

        Backs the gateway's public readiness probe so the chat UI can gate input
        until vLLM has finished starting. Never raises — any error reads as
        "not ready" rather than surfacing an exception to the caller.
        """
        try:
            ready = bool(self.llm_client and self.llm_client.is_available())
        except Exception as e:
            self.logger.log(
                "service:model",
                "LLM readiness probe failed",
                {"error": str(e)},
                hypothesis_id="W",
            )
            ready = False
        return {"ready": ready, "implementation": self.config.llm_implementation}

    def get_model_info(self, model: str) -> Dict[str, Any]:
        """
        Get information about a specific model.
        
        Args:
            model: Model name
            
        Returns:
            Dictionary with model information
        """
        if not model:
            raise ValidationException("Model name is required")
        
        self.logger.log("service:model", "Getting model info", {"model": model})
        
        info = {
            "name": model,
            "implementation": self.config.llm_implementation,
            "status": "available"
        }
        
        # Try to get additional info from the client
        if hasattr(self.llm_client, "get_model_info"):
            client_info = self.llm_client.get_model_info(model)
            if client_info:
                info.update(client_info)
        
        # Check if model is downloaded (for Hugging Face)
        if self.config.llm_implementation == LLMImplementation.HUGGINGFACE:
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            model_path = os.path.join(cache_dir, f"models--{model.replace('/', '--')}")
            if os.path.exists(model_path):
                info["downloaded"] = True
                info["cache_path"] = model_path
            else:
                info["downloaded"] = False
        
        return info
    
    def get_download_status(self, model: str) -> Dict[str, Any]:
        """
        Get download status for a model.
        
        Args:
            model: Model name
            
        Returns:
            Dictionary with download status
        """
        with self._download_lock:
            status = self._download_status.get(model, {
                "status": "not_started",
                "progress": 0
            })
        
        return {
            "model": model,
            **status
        }
    
    def start_download(self, model: str, implementation: str = "huggingface") -> Dict[str, Any]:
        """
        Start downloading a model (non-blocking).
        
        Args:
            model: Model name
            implementation: Implementation type (huggingface, vllm)
            
        Returns:
            Dictionary with download status
        """
        if not model:
            raise ValidationException("Model name is required")
        
        # Check if already downloading
        with self._download_lock:
            if model in self._download_status:
                status = self._download_status[model]
                if status["status"] == "downloading":
                    return {
                        "status": "already_downloading",
                        "model": model,
                        "progress": status.get("progress", 0)
                    }
            
            self._download_status[model] = {
                "status": "downloading",
                "progress": 0
            }
        
        # Start download in background thread
        thread = threading.Thread(
            target=self._download_model_thread,
            args=(model, implementation),
            daemon=True
        )
        thread.start()
        
        self.logger.log(
            "service:model",
            "Model download started",
            {"model": model, "implementation": implementation}
        )
        
        return {
            "status": "download_started",
            "model": model,
            "message": f"Download started for {model}"
        }
    
    def _download_model_thread(self, model: str, implementation: str) -> None:
        """Download model in background thread."""
        try:
            if implementation == LLMImplementation.HUGGINGFACE:
                self._download_huggingface_model(model)
            elif implementation == LLMImplementation.VLLM:
                raise NotImplementedError("vLLM model download should be handled by vLLM server")
            else:
                raise ValueError(f"Unsupported implementation: {implementation}")
            
            with self._download_lock:
                self._download_status[model] = {
                    "status": "completed",
                    "progress": 100
                }
            
            self.logger.log(
                "service:model",
                "Model download completed",
                {"model": model}
            )
        except Exception as e:
            with self._download_lock:
                self._download_status[model] = {
                    "status": "error",
                    "error": str(e)
                }
            
            self.logger.log(
                "service:model",
                "Model download failed",
                {"model": model, "error": str(e)},
                hypothesis_id="E"
            )
    
    def _download_huggingface_model(self, model: str) -> None:
        """Download Hugging Face model."""
        try:
            from transformers import AutoModel, AutoTokenizer
            
            # Update download status
            with self._download_lock:
                if model in self._download_status:
                    self._download_status[model]["progress"] = 25
            
            # Download tokenizer (cached for later loads; handle not needed here)
            AutoTokenizer.from_pretrained(model)
            
            with self._download_lock:
                if model in self._download_status:
                    self._download_status[model]["progress"] = 50
            
            # Download model
            AutoModel.from_pretrained(model)
            
            with self._download_lock:
                if model in self._download_status:
                    self._download_status[model]["progress"] = 100
            
        except Exception as e:
            raise ServiceException(f"Failed to download Hugging Face model: {str(e)}", original_exception=e)
    
    def list_implementations(self) -> Dict[str, Any]:
        """
        List available LLM implementations.
        
        Returns:
            Dictionary with implementations list
        """
        implementations = [
            {
                "name": "huggingface",
                "display_name": "Hugging Face Transformers",
                "description": "Local models using transformers library",
                "supports_download": True,
                "supports_finetuning": True,
                "concurrent_requests": True
            },
            {
                "name": "vllm",
                "display_name": "vLLM",
                "description": "High-performance inference server",
                "supports_download": False,
                "supports_finetuning": False,
                "concurrent_requests": True
            },
            {
                "name": "ollama",
                "display_name": "Ollama",
                "description": "Local LLM runtime (legacy)",
                "supports_download": False,
                "supports_finetuning": False,
                "concurrent_requests": False
            }
        ]
        
        return {
            "implementations": implementations,
            "current": self.config.llm_implementation
        }
    
    def get_implementation_info(self, implementation: str) -> Dict[str, Any]:
        """
        Get information about a specific implementation.
        
        Args:
            implementation: Implementation name
            
        Returns:
            Dictionary with implementation information
        """
        info = {
            "huggingface": {
                "name": "huggingface",
                "display_name": "Hugging Face Transformers",
                "description": "Local models using transformers library with GPU support",
                "features": ["GPU acceleration", "Model caching", "Concurrent requests", "Fine-tuning support"],
                "requirements": ["PyTorch", "Transformers library"],
                "config": {
                    "device": self.config.device,
                    "max_concurrent_requests": self.config.max_concurrent_requests
                }
            },
            "vllm": {
                "name": "vllm",
                "display_name": "vLLM",
                "description": "High-performance inference server optimized for throughput",
                "features": ["High throughput", "Continuous batching", "PagedAttention", "Concurrent requests"],
                "requirements": ["vLLM server running"],
                "config": {
                    "base_url": self.config.vllm_base_url
                }
            },
            "ollama": {
                "name": "ollama",
                "display_name": "Ollama",
                "description": "Local LLM runtime (legacy support)",
                "features": ["Easy setup", "Local execution"],
                "requirements": ["Ollama installed"],
                "config": {
                    "ollama_url": self.config.ollama_url
                }
            }
        }
        
        if implementation in info:
            return info[implementation]
        else:
            raise NotFoundException(f"Unknown implementation: {implementation}")
