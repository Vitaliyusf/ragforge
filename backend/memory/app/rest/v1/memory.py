"""Memory service REST API endpoints."""
from fastapi import APIRouter, Depends, status

from app.rest.controllers import MemoryController
from app.rest.dependencies import service_container
from app.schemas.chat import ChatListResponse, ChatResponse, CreateChatRequest
from app.schemas.message import AddMessageRequest, MessageListResponse, MessageResponse
from app.services.chat_service import ChatService
from app.services.message_service import MessageService
from shared.http_auth import require_internal_identity


router = APIRouter(dependencies=[Depends(require_internal_identity)])
controller = MemoryController()


@router.post("/chats", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    request: CreateChatRequest,
    chat_service: ChatService = Depends(service_container.get_chat_service),
):
    """Create a chat document from the supplied identifier and title."""
    return controller.create_chat(request, chat_service)


@router.get("/chats", response_model=ChatListResponse)
async def get_chats(
    chat_service: ChatService = Depends(service_container.get_chat_service)
):
    """Return all stored chats ordered by most recent update."""
    return controller.get_chats(chat_service)


@router.get("/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: str,
    chat_service: ChatService = Depends(service_container.get_chat_service)
):
    """Return one stored chat by identifier."""
    return controller.get_chat(chat_id, chat_service)


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: str,
    chat_service: ChatService = Depends(service_container.get_chat_service),
    message_service: MessageService = Depends(service_container.get_message_service)
):
    """Delete a chat and its associated messages."""
    return controller.delete_chat(chat_id, chat_service, message_service)


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_message(
    request: AddMessageRequest,
    message_service: MessageService = Depends(service_container.get_message_service),
):
    """Persist a message and update the chat timestamp."""
    return controller.add_message(request, message_service)


@router.get("/chats/{chat_id}/messages", response_model=MessageListResponse)
async def get_messages(
    chat_id: str,
    message_service: MessageService = Depends(service_container.get_message_service)
):
    """Return the ordered message history for one chat."""
    return controller.get_messages(chat_id, message_service)


@router.get("/health")
async def health(
    chat_service: ChatService = Depends(service_container.get_chat_service)
):
    """Report REST-level health from RabbitMQ consumer visibility and chat-count access."""
    return controller.health(chat_service)
