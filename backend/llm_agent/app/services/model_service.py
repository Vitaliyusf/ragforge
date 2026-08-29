"""Model discovery for the externally managed vLLM runtime."""
from typing import Any, Dict

from app.cache.interfaces import IModelCache
from app.core.config import Settings
from app.core.errors import NotFoundException, ServiceException, ValidationException
from app.llm.interfaces import ILLMClient
from app.services.base import BaseService
from shared.logging import ServiceLogger


class ModelService(BaseService):
    """Expose vLLM model state without owning downloads or provider switching."""

    def __init__(
        self,
        llm_client: ILLMClient,
        model_cache: IModelCache,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        super().__init__(llm_client, logger, config)
        self.model_cache = model_cache

    def list_models(self) -> Dict[str, Any]:
        try:
            if not self.model_cache.is_valid():
                self.model_cache.set_models(self.llm_client.list_models())
            models = self.model_cache.get_models() or [self.config.default_model]
            return {
                "status": "success",
                "models": [self.get_model_info(str(model)) for model in models],
                "count": len(models),
                "default": self.config.default_model,
                "cached": self.model_cache.is_valid(),
                "last_updated": (
                    self.model_cache.get_last_updated().isoformat()
                    if self.model_cache.get_last_updated() is not None
                    else None
                ),
            }
        except Exception as exc:
            raise ServiceException(f"Failed to list models: {exc}", original_exception=exc) from exc

    def llm_ready(self) -> Dict[str, Any]:
        try:
            ready = bool(self.llm_client.is_available())
        except Exception:
            ready = False
        return {"ready": ready, "implementation": "vllm"}

    def get_model_info(self, model: str) -> Dict[str, Any]:
        if not model:
            raise ValidationException("Model name is required")
        info: Dict[str, Any] = {"name": model, "implementation": "vllm", "status": "available"}
        client_method = getattr(self.llm_client, "get_model_info", None)
        if callable(client_method):
            client_info = client_method(model)
            if client_info:
                info.update(client_info)
        return info

    def get_download_status(self, model: str) -> Dict[str, Any]:
        if not model:
            raise ValidationException("Model name is required")
        return {"model": model, "status": "externally_managed", "progress": None}

    def start_download(self, model: str, implementation: str = "vllm") -> Dict[str, Any]:
        if not model:
            raise ValidationException("Model name is required")
        raise ValidationException("Model downloads are managed by the vLLM runtime image")

    def list_implementations(self) -> Dict[str, Any]:
        return {
            "implementations": [
                {
                    "name": "vllm",
                    "display_name": "vLLM",
                    "description": "Externally managed production inference server",
                    "supports_download": False,
                    "supports_finetuning": False,
                    "concurrent_requests": True,
                }
            ],
            "current": "vllm",
        }

    def get_implementation_info(self, implementation: str) -> Dict[str, Any]:
        if implementation != "vllm":
            raise NotFoundException(f"Unknown implementation: {implementation}")
        return {
            "name": "vllm",
            "display_name": "vLLM",
            "description": "Externally managed production inference server",
            "features": ["High throughput", "Continuous batching", "Concurrent requests"],
            "requirements": ["vLLM server running"],
            "config": {"base_url": self.config.vllm_base_url},
        }
