"""Config management service — configuration and generation-params CRUD."""
from __future__ import annotations

from typing import Any, Dict

from app.core.constants import ConfigManagementAction, LLMImplementation
from app.core.errors import ValidationError
from app.services.base import BaseRPCService


class ConfigManagementService(BaseRPCService):
    """RabbitMQ-backed facade for the config management service."""

    async def get_config(self) -> Dict[str, Any]:
        """Fetch the current service configuration."""
        return await self._send(
            self.config.request_topics["config_management"],
            {"action": ConfigManagementAction.GET_CONFIG},
        )

    async def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Apply partial configuration updates."""
        return await self._send_long(
            self.config.request_topics["config_management"],
            {"action": ConfigManagementAction.UPDATE_CONFIG, "updates": updates},
        )

    async def get_generation_params(self) -> Dict[str, Any]:
        """Fetch the current LLM generation parameters."""
        return await self._send(
            self.config.request_topics["config_management"],
            {"action": ConfigManagementAction.GET_GENERATION_PARAMS},
        )

    async def update_generation_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update LLM generation parameters."""
        return await self._send_long(
            self.config.request_topics["config_management"],
            {"action": ConfigManagementAction.UPDATE_GENERATION_PARAMS, "params": params},
        )

    async def switch_implementation(self, implementation: str) -> Dict[str, Any]:
        """Switch the active LLM implementation.

        Raises:
            ValidationError: If ``implementation`` is not a known ``LLMImplementation`` value.
        """
        valid = {m.value for m in LLMImplementation}
        if implementation not in valid:
            raise ValidationError(
                f"Invalid implementation: {implementation!r}. Must be one of: {', '.join(sorted(valid))}"
            )
        return await self._send_long(
            self.config.request_topics["config_management"],
            {"action": ConfigManagementAction.SWITCH_IMPLEMENTATION, "implementation": implementation},
        )

    async def get_model_configs(self) -> Dict[str, Any]:
        """Fetch all model configurations."""
        return await self._send(
            self.config.request_topics["config_management"],
            {"action": ConfigManagementAction.GET_MODEL_CONFIGS},
        )

    async def update_model_configs(self, model_configs: Dict[str, Any]) -> Dict[str, Any]:
        """Update model configurations."""
        return await self._send_long(
            self.config.request_topics["config_management"],
            {"action": ConfigManagementAction.UPDATE_MODEL_CONFIGS, "model_configs": model_configs},
        )
