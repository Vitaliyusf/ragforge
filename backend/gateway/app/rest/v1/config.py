"""Read-only effective-configuration API route."""
from fastapi import APIRouter, Depends

from app.core.auth import require_admin
from app.core.deps import get_config_management_service
from app.core.errors import handle_exception
from app.services.config_management_service import ConfigManagementService

router = APIRouter(prefix="/config", tags=["config"], dependencies=[Depends(require_admin)])


@router.get("")
async def get_config_endpoint(
    service: ConfigManagementService = Depends(get_config_management_service),
):
    """Get startup-effective deployment configuration."""
    try:
        return await service.get_config()
    except Exception as exc:
        raise handle_exception(exc)
