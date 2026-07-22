"""Configuration read/write RabbitMQ handler."""
from typing import Any, Dict

from app.messaging.base_handler import BaseRabbitMQHandler
from app.messaging.interfaces import IProducer
from app.core.config import Settings
from app.core.constants import VALID_IMPLEMENTATIONS, ConfigAction
from app.core.logging_config import ServiceLogger
from app.services.config_service import ConfigService

try:
    from shared.schemas.message_schemas import ConfigManagementRequest
    _HAS_SCHEMAS = True
except ImportError:
    _HAS_SCHEMAS = False


class ConfigManagementHandler(BaseRabbitMQHandler):
    """Handle configuration read/write actions using a dispatch table."""

    def __init__(
        self,
        producer: IProducer,
        config_service: ConfigService,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        super().__init__(producer, logger, config)
        self.config_service = config_service
        self._dispatch = {
            ConfigAction.GET_CONFIG:            lambda m: self.config_service.get_config(),
            ConfigAction.UPDATE_CONFIG:         lambda m: self.config_service.update_config(m.get("updates", {})),
            ConfigAction.GET_GENERATION_PARAMS: lambda m: self.config_service.get_generation_params(),
            ConfigAction.GET_MODEL_CONFIGS:     lambda m: self.config_service.get_model_configs(),
            ConfigAction.UPDATE_MODEL_CONFIGS:  lambda m: self.config_service.update_model_configs(
                                                    m.get("model_configs", {})
                                                ),
        }

    def handle(self, message: Dict[str, Any]) -> None:
        normalized = self.normalize_correlated_request(message)
        if _HAS_SCHEMAS:
            validated, error = self._validate(normalized, ConfigManagementRequest)
            if error:
                self.logger.log("rabbitmq:config_management", "Schema validation failed", {"error": error}, hypothesis_id="E")
                self._send_error(normalized, error, error_code="invalid_request", status_code=400)
                return

        action = normalized.get("action")

        # Implementation switch is handled upstream in main.py; we only
        # acknowledge the request here so the gateway gets a response.
        if action == ConfigAction.SWITCH_IMPLEMENTATION:
            implementation = normalized.get("implementation")
            if implementation not in VALID_IMPLEMENTATIONS:
                self._send_error(
                    normalized,
                    f"Invalid implementation: {implementation}",
                    error_code="invalid_request",
                    status_code=400,
                )
                return
            self._send_response(
                normalized,
                {
                    "status": "switch_requested",
                    "implementation": implementation,
                    "message": "Implementation switch will be processed",
                },
            )
            return

        handler_fn = self._dispatch.get(action)
        if not handler_fn:
            self._send_error(normalized, f"Unknown action: {action}", error_code="invalid_request", status_code=400)
            return

        try:
            self._send_response(normalized, handler_fn(normalized))
        except Exception as e:
            self.logger.log(
                "rabbitmq:config_management",
                "Error processing config management request",
                {"action": action, "error": str(e)},
                hypothesis_id="E",
            )
            self._send_exception(normalized, e)
