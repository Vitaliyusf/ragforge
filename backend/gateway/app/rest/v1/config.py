"""Configuration management API routes."""
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_config_management_service
from app.core.errors import handle_exception
from app.services.config_management_service import ConfigManagementService
from app.core.auth import require_admin

router = APIRouter(prefix="/config", tags=["config"], dependencies=[Depends(require_admin)])


@router.get("")
async def get_config_endpoint(
    service: ConfigManagementService = Depends(get_config_management_service),
):
    """Get current configuration."""
    try:
        return await service.get_config()
    except Exception as e:
        raise handle_exception(e)


@router.post("")
async def update_config(
    updates: Dict[str, Any],
    service: ConfigManagementService = Depends(get_config_management_service),
):
    """Update configuration."""
    try:
        return await service.update_config(updates)
    except Exception as e:
        raise handle_exception(e)


@router.get("/generation-params")
async def get_generation_params(
    service: ConfigManagementService = Depends(get_config_management_service),
):
    """Get generation parameters."""
    try:
        return await service.get_generation_params()
    except Exception as e:
        raise handle_exception(e)


@router.post("/generation-params")
async def update_generation_params(
    params: Dict[str, Any],
    service: ConfigManagementService = Depends(get_config_management_service),
):
    """Update generation parameters."""
    try:
        return await service.update_generation_params(params)
    except Exception as e:
        raise handle_exception(e)


@router.post("/switch-implementation")
async def switch_implementation(
    implementation: str = Query(...),
    service: ConfigManagementService = Depends(get_config_management_service),
):
    """Switch LLM implementation."""
    try:
        return await service.switch_implementation(implementation)
    except Exception as e:
        raise handle_exception(e)


@router.get("/models")
async def get_model_configs(
    service: ConfigManagementService = Depends(get_config_management_service),
):
    """Get model configurations."""
    try:
        return await service.get_model_configs()
    except Exception as e:
        raise handle_exception(e)


@router.post("/models")
async def update_model_configs(
    model_configs: Dict[str, Any],
    service: ConfigManagementService = Depends(get_config_management_service),
):
    """Update model configurations."""
    try:
        return await service.update_model_configs(model_configs)
    except Exception as e:
        raise handle_exception(e)
