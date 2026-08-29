"""Model management API routes."""
from fastapi import APIRouter, Depends, Query

from app.core.deps import get_model_management_service
from app.core.errors import handle_exception
from app.services.model_management_service import ModelManagementService
from app.core.auth import require_admin

router = APIRouter(prefix="/model-management", tags=["models"], dependencies=[Depends(require_admin)])


@router.get("/implementations")
async def get_implementations(
    service: ModelManagementService = Depends(get_model_management_service),
):
    """Get available LLM implementations.

    Returns an empty implementations list when RabbitMQ or the llm_agent service
    is unavailable so the frontend can render without a console error.
    """
    try:
        return await service.list_implementations()
    except Exception as e:
        raise handle_exception(e)


@router.get("/implementations/{implementation}")
async def get_implementation_info(
    implementation: str,
    service: ModelManagementService = Depends(get_model_management_service),
):
    """Get information about a specific implementation."""
    try:
        return await service.get_implementation_info(implementation)
    except Exception as e:
        raise handle_exception(e)


@router.get("/models")
async def list_all_models(
    service: ModelManagementService = Depends(get_model_management_service),
):
    """List all available models with details."""
    try:
        return await service.list_all_models()
    except Exception as e:
        raise handle_exception(e)


@router.get("/models/{model}")
async def get_model_info(
    model: str,
    service: ModelManagementService = Depends(get_model_management_service),
):
    """Get detailed information about a specific model."""
    try:
        return await service.get_model_info(model)
    except Exception as e:
        raise handle_exception(e)


@router.post("/models/{model}/download")
async def download_model(
    model: str,
    implementation: str = Query(default="vllm"),
    service: ModelManagementService = Depends(get_model_management_service),
):
    """Download a model."""
    try:
        return await service.download_model(model, implementation)
    except Exception as e:
        raise handle_exception(e)


@router.get("/models/{model}/download-status")
async def get_download_status(
    model: str,
    service: ModelManagementService = Depends(get_model_management_service),
):
    """Get download status for a model."""
    try:
        return await service.get_download_status(model)
    except Exception as e:
        raise handle_exception(e)
