"""Gateway service entry point — app construction, lifecycle, and DI singletons."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from app.core.config import GatewayConfig
from app.core.exception_handlers import (
    register_exception_handlers,  # re-exported for tests that import from app.main
)
from app.core.http_middleware import CorrelationMiddleware
from shared.logging import ServiceLogger, setup_logging
from app.core.rabbitmq_client import RabbitMQClient
from app.core.rpc_client import GatewayRPCClient
from app.db.session import close_db, get_db, init_db
from app.rest.routes import setup_routes
from app.services.chat_history_service import ChatHistoryService
from app.services.chat_service import ChatService
from app.services.config_management_service import ConfigManagementService
from app.services.file_service import FileService
from app.services.log_service import LogService
from app.services.metrics_service import MetricsService
from app.services.long_term_memory_service import LongTermMemoryService
from app.services.model_management_service import ModelManagementService
from app.services.prometheus_client import PrometheusClient
from app.services.rag_service import RagService
from app.services.auth_service import AuthService
from shared.rate_limiter import RateLimiterMiddleware
from shared.security import SecurityHeadersMiddleware

# ── Optional telemetry ───────────────────────────────────────────────────────────

try:
    from shared.metrics import setup_metrics
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

# ── Service singletons (populated in lifespan) ────────────────────────────────

_config: Optional[GatewayConfig] = None
_logger: Optional[ServiceLogger] = None
_rabbitmq_client: Optional[RabbitMQClient] = None
_rpc_client: Optional[GatewayRPCClient] = None
_chat_history_service: Optional[ChatHistoryService] = None
_chat_service: Optional[ChatService] = None
_config_management_service: Optional[ConfigManagementService] = None
_file_service: Optional[FileService] = None
_log_service: Optional[LogService] = None
_metrics_service: Optional[MetricsService] = None
_long_term_memory_service: Optional[LongTermMemoryService] = None
_model_management_service: Optional[ModelManagementService] = None
_prometheus_client: Optional[PrometheusClient] = None
_rag_service: Optional[RagService] = None
_auth_service: Optional[AuthService] = None


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _logger, _rabbitmq_client, _rpc_client
    global _chat_history_service, _chat_service, _config_management_service
    global _file_service, _log_service, _long_term_memory_service
    global _model_management_service, _rag_service, _auth_service
    global _prometheus_client, _metrics_service

    _config = GatewayConfig()
    _logger = setup_logging(_config.service_name)
    app.state.service_logger = _logger

    _logger.log("main:startup", "Gateway service starting up")

    init_db(_config.mongo_connection_string, _config.mongo_database_name)
    _auth_service = AuthService(get_db(), _config)
    _auth_service.ensure_indexes()
    _auth_service.bootstrap_admin()

    _rpc_client = GatewayRPCClient(_config, _logger)
    await _rpc_client.connect()
    _rabbitmq_client = RabbitMQClient(_rpc_client, _logger, _config)

    _chat_history_service    = ChatHistoryService(_rabbitmq_client, _logger, _config)
    _chat_service            = ChatService(_rabbitmq_client, _logger, _config, chat_history_service=_chat_history_service)
    _config_management_service = ConfigManagementService(_rabbitmq_client, _logger, _config)
    _file_service            = FileService(_rabbitmq_client, _logger, _config)
    _log_service             = LogService()
    _long_term_memory_service = LongTermMemoryService(_rabbitmq_client, _logger, _config)
    _model_management_service = ModelManagementService(_rabbitmq_client, _logger, _config)
    _rag_service             = RagService(_rabbitmq_client, _logger, _config)
    _prometheus_client       = PrometheusClient(_config.prometheus_url)
    _metrics_service         = MetricsService(_rabbitmq_client, _logger, _config, _prometheus_client)

    _logger.log("main:startup", "Gateway service startup complete")
    try:
        yield
    finally:
        _logger.log("main:shutdown", "Gateway service shutting down")
        await _rpc_client.close()
        await _prometheus_client.aclose()
        close_db()


# ── App construction ──────────────────────────────────────────────────────────

app = FastAPI(title="Gateway Service", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimiterMiddleware, global_rate=100.0, per_ip_rate=20.0, burst_multiplier=2.0)

app.add_middleware(CorrelationMiddleware)

if _HAS_METRICS:
    setup_metrics(app, "gateway")

setup_routes(app)
register_exception_handlers(app)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    _cfg = GatewayConfig()
    uvicorn.run(app, host=_cfg.service_host, port=_cfg.service_port)
