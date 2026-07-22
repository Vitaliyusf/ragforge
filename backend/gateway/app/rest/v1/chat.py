"""Chat API routes."""
from fastapi import APIRouter, Depends

from app.core.deps import get_chat_service
from app.core.errors import handle_exception
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.core.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(get_current_user)])


@router.post("")
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
):
    """Chat endpoint."""
    try:
        return await service.process_chat(request)
    except Exception as e:
        raise handle_exception(e)
