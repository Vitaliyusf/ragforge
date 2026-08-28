"""Read-only facade for deployment-owned LLM configuration."""
from __future__ import annotations

from typing import Any, Dict

from app.core.constants import ConfigManagementAction
from app.services.base import BaseRPCService


class ConfigManagementService(BaseRPCService):
    """RabbitMQ-backed facade for startup-effective configuration."""

    async def get_config(self) -> Dict[str, Any]:
        """Fetch the current service configuration."""
        return await self._send(
            self.config.request_topics["config_management"],
            {"action": ConfigManagementAction.GET_CONFIG},
        )
