"""LLM runtime status routes for the chat UI."""
from fastapi import APIRouter, Depends

from app.core.deps import get_model_management_service
from app.core.errors import handle_exception
from app.services.model_management_service import ModelManagementService
from app.core.auth import get_current_user

router = APIRouter(prefix="/llm", tags=["llm"], dependencies=[Depends(get_current_user)])


@router.get("/ready")
async def llm_ready(
    service: ModelManagementService = Depends(get_model_management_service),
):
    """Report whether the LLM backend (vLLM) has finished starting.

    Polled by the chat UI to keep the composer disabled until the model is
    actually available. Any backend/transport error degrades to
    ``{"ready": False}`` rather than raising, so the chat simply stays disabled.
    """
    try:
        return await service.llm_ready()
    except Exception as e:
        raise handle_exception(e)
