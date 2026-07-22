"""Chat history API routes."""
from fastapi import APIRouter, Depends, Query

from app.core.deps import get_chat_history_service
from app.core.errors import handle_exception
from app.schemas.message import MessageRequest
from app.services.chat_history_service import ChatHistoryService
from app.core.auth import get_current_user

router = APIRouter(prefix="/chats", tags=["chat-history"], dependencies=[Depends(get_current_user)])


@router.post("")
async def create_chat(
    title: str = Query(default="New Chat"),
    service: ChatHistoryService = Depends(get_chat_history_service)
):
    """Create a new chat."""
    try:
        return await service.create_chat(title)
    except Exception as e:
        raise handle_exception(e)


@router.get("")
async def get_chats(
    service: ChatHistoryService = Depends(get_chat_history_service)
):
    """Get all chats."""
    try:
        return await service.get_chats()
    except Exception as e:
        raise handle_exception(e)


@router.get("/{chat_id}/messages")
async def get_messages(
    chat_id: str,
    service: ChatHistoryService = Depends(get_chat_history_service)
):
    """Get messages for a chat."""
    try:
        return await service.get_messages(chat_id)
    except Exception as e:
        raise handle_exception(e)


@router.post("/{chat_id}/messages")
async def add_message(
    chat_id: str,
    request: MessageRequest,
    service: ChatHistoryService = Depends(get_chat_history_service)
):
    """Add a message to a chat."""
    try:
        return await service.add_message(chat_id, request)
    except Exception as e:
        raise handle_exception(e)


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    service: ChatHistoryService = Depends(get_chat_history_service)
):
    """Delete a chat."""
    try:
        return await service.delete_chat(chat_id)
    except Exception as e:
        raise handle_exception(e)


@router.post("/{chat_id}/process-exit")
async def process_chat_exit(
    chat_id: str,
    service: ChatHistoryService = Depends(get_chat_history_service)
):
    """Process chat exit - generate headline and extract memory."""
    try:
        return await service.process_chat_exit(chat_id)
    except Exception as e:
        raise handle_exception(e)


@router.patch("/{chat_id}/title")
async def update_chat_title(
    chat_id: str,
    title: str = Query(...),
    service: ChatHistoryService = Depends(get_chat_history_service)
):
    """Update chat title."""
    try:
        return await service.update_chat_title(chat_id, title)
    except Exception as e:
        raise handle_exception(e)
