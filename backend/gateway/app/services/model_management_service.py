"""Model management service — LLM implementation and model lifecycle operations."""
from __future__ import annotations

from typing import Any, Dict

from app.core.constants import ModelManagementAction
from app.core.errors import RPCConnectionError, RPCTimeoutError
from app.services.base import BaseRPCService


class ModelManagementService(BaseRPCService):
    """RabbitMQ-backed facade for LLM implementation and model management."""

    async def llm_ready(self) -> Dict[str, Any]:
        """Report whether the LLM backend (e.g. vLLM) has finished starting.

        Backs the public readiness probe the chat UI polls to gate its input.
        Returns ``{"ready": False}`` when RabbitMQ or the llm_agent service is
        unavailable, so "not reachable yet" reads as "not ready" rather than an
        error the frontend has to special-case.
        """
        try:
            return await self._send(
                self.config.request_topics["model_management"],
                {"action": ModelManagementAction.LLM_READY},
            )
        except (RPCTimeoutError, RPCConnectionError):
            return {"ready": False}

    async def list_implementations(self) -> Dict[str, Any]:
        """List available LLM implementations.

        Returns an empty fallback when RabbitMQ or the llm_agent service is unavailable,
        so the frontend can render without a console error.
        """
        try:
            return await self._send(
                self.config.request_topics["model_management"],
                {"action": ModelManagementAction.LIST_IMPLEMENTATIONS},
            )
        except (RPCTimeoutError, RPCConnectionError):
            return {"implementations": [], "current": None}

    async def get_implementation_info(self, implementation: str) -> Dict[str, Any]:
        """Fetch details about a specific LLM implementation."""
        return await self._send(
            self.config.request_topics["model_management"],
            {"action": ModelManagementAction.GET_IMPLEMENTATION_INFO, "implementation": implementation},
        )

    async def list_all_models(self) -> Dict[str, Any]:
        """List all available models with details."""
        return await self._send_long(
            self.config.request_topics["model_management"],
            {"action": ModelManagementAction.LIST_MODELS},
        )

    async def get_model_info(self, model: str) -> Dict[str, Any]:
        """Fetch details about a specific model."""
        return await self._send(
            self.config.request_topics["model_management"],
            {"action": ModelManagementAction.GET_MODEL_INFO, "model": model},
        )

    async def download_model(self, model: str, implementation: str) -> Dict[str, Any]:
        """Trigger a model download."""
        return await self._send_long(
            self.config.request_topics["model_management"],
            {"action": ModelManagementAction.DOWNLOAD_MODEL, "model": model, "implementation": implementation},
        )

    async def get_download_status(self, model: str) -> Dict[str, Any]:
        """Get the current download status for a model."""
        return await self._send(
            self.config.request_topics["model_management"],
            {"action": ModelManagementAction.GET_DOWNLOAD_STATUS, "model": model},
        )
