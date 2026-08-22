"""Model listing and management RabbitMQ handlers."""
from typing import Any, Dict

from app.messaging.base_handler import BaseRabbitMQHandler
from app.messaging.interfaces import IProducer
from app.core.config import Settings
from app.core.logging_config import ServiceLogger
from app.services.model_service import ModelService

try:
    from shared.schemas.message_schemas import ModelRequest, ModelManagementRequest
    _HAS_SCHEMAS = True
except ImportError:
    _HAS_SCHEMAS = False


class ModelHandler(BaseRabbitMQHandler):
    """Handle simple model-listing requests (correlated, gateway waits)."""

    def __init__(
        self,
        producer: IProducer,
        model_service: ModelService,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        super().__init__(producer, logger, config)
        self.model_service = model_service

    def handle(self, message: Dict[str, Any]) -> None:
        normalized = self.normalize_correlated_request(message)
        if _HAS_SCHEMAS:
            validated, error = self._validate(normalized, ModelRequest)
            if error:
                self.logger.log("rabbitmq:model", "Schema validation failed", {"error": error}, hypothesis_id="E")
                self._send_error(normalized, error, error_code="invalid_request", status_code=400)
                return

        correlation_id = normalized.get("correlation_id")
        self.logger.log("rabbitmq:model", "Processing model request", {"correlation_id": correlation_id})

        try:
            self._send_response(normalized, self.model_service.list_models())
        except Exception as e:
            self.logger.log(
                "rabbitmq:model",
                "Error processing model request",
                {"correlation_id": correlation_id, "error": str(e)},
                hypothesis_id="E",
            )
            self._send_exception(normalized, e)


class ModelManagementHandler(BaseRabbitMQHandler):
    """Handle model-management actions using a dispatch table."""

    def __init__(
        self,
        producer: IProducer,
        model_service: ModelService,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        super().__init__(producer, logger, config)
        self.model_service = model_service
        self._dispatch = {
            "list_models":             lambda m: self.model_service.list_models(),
            "get_model_info":          lambda m: self.model_service.get_model_info(m.get("model")),
            "download_model":          lambda m: self.model_service.start_download(
                                           m.get("model"), m.get("implementation", "huggingface")
                                       ),
            "get_download_status":     lambda m: self.model_service.get_download_status(m.get("model")),
            "llm_ready":               lambda m: self.model_service.llm_ready(),
            "list_implementations":    lambda m: self.model_service.list_implementations(),
            "get_implementation_info": lambda m: self.model_service.get_implementation_info(
                                           m.get("implementation")
                                       ),
        }

    def handle(self, message: Dict[str, Any]) -> None:
        normalized = self.normalize_correlated_request(message)
        if _HAS_SCHEMAS:
            validated, error = self._validate(normalized, ModelManagementRequest)
            if error:
                self.logger.log("rabbitmq:model_management", "Schema validation failed", {"error": error}, hypothesis_id="E")
                self._send_error(normalized, error, error_code="invalid_request", status_code=400)
                return

        action = normalized.get("action")

        handler_fn = self._dispatch.get(action)
        if not handler_fn:
            self._send_error(normalized, f"Unknown action: {action}", error_code="invalid_request", status_code=400)
            return

        try:
            self._send_response(normalized, handler_fn(normalized))
        except Exception as e:
            self.logger.log(
                "rabbitmq:model_management",
                "Error processing model management request",
                {"action": action, "error": str(e)},
                hypothesis_id="E",
            )
            self._send_exception(normalized, e)
