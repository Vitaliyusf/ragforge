"""Log API routes."""
from fastapi import APIRouter, Depends, Query

from app.core.deps import get_log_service, get_config
from app.services.log_service import LogService
from app.core.auth import require_admin
from shared.auth import AuthIdentity

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/{service}")
async def get_logs(
    service: str,
    lines: int = Query(default=100, ge=1, le=1000),
    identity: AuthIdentity = Depends(require_admin),
    config = Depends(get_config),
    log_service: LogService = Depends(get_log_service)
):
    """Get logs for a specific service."""
    if service not in config.log_services_list:
        return {"service": service, "logs": [], "source": "denied"}
    return log_service.get_logs(service, lines, tenant_id=identity.tenant_id)


@router.get("")
async def get_all_logs(
    lines: int = Query(default=50, ge=1, le=1000),
    identity: AuthIdentity = Depends(require_admin),
    log_service: LogService = Depends(get_log_service),
    config = Depends(get_config)
):
    """Get logs from all services."""
    return log_service.get_all_logs(config.log_services_list, lines, tenant_id=identity.tenant_id)
