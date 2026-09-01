"""REST controllers for memory service endpoints."""
from app.rest.base import EndpointController
from app.schemas.chat import ChatListResponse, ChatResponse, CreateChatRequest
from app.schemas.message import AddMessageRequest, MessageListResponse, MessageResponse
from app.services.chat_service import ChatService
from app.services.message_service import MessageService


class MemoryController(EndpointController):
    """Controller implementing the memory REST surface."""

    def create_chat(self, request: CreateChatRequest, chat_service: ChatService) -> ChatResponse:
        """Create a chat document from the supplied identifier and title."""
        return self.execute(
            lambda: ChatResponse(**chat_service.create_chat(request.chat_id, request.title))
        )

    def get_chats(self, chat_service: ChatService) -> ChatListResponse:
        """Return all stored chats ordered by most recent update."""
        return self.execute(
            lambda: ChatListResponse(
                chats=[ChatResponse(**chat) for chat in chat_service.get_all_chats()]
            )
        )

    def get_chat(self, chat_id: str, chat_service: ChatService) -> ChatResponse:
        """Return one stored chat by identifier."""
        return self.execute(lambda: ChatResponse(**chat_service.get_chat(chat_id)))

    def delete_chat(self, chat_id: str, chat_service: ChatService, message_service: MessageService) -> None:
        """Delete a chat and its associated messages."""
        def operation() -> None:
            message_service.delete_messages_by_chat(chat_id)
            chat_service.delete_chat(chat_id)
            return None

        return self.execute(operation)

    def add_message(self, request: AddMessageRequest, message_service: MessageService) -> MessageResponse:
        """Persist a message and update the chat timestamp."""
        return self.execute(
            lambda: MessageResponse(
                **message_service.add_message(
                    request.message_id,
                    request.chat_id,
                    request.sender,
                    request.message,
                    request.metadata,
                )
            )
        )

    def get_messages(self, chat_id: str, message_service: MessageService) -> MessageListResponse:
        """Return the ordered message history for one chat."""
        return self.execute(
            lambda: MessageListResponse(
                messages=[MessageResponse(**message) for message in message_service.get_messages(chat_id)]
            )
        )

    def health(self, chat_service: ChatService) -> dict:
        """Report REST-level health from chat-count access."""
        def operation() -> dict:
            try:
                chat_count = len(chat_service.get_all_chats())
            except Exception:
                chat_count = -1

            return {
                "status": "ok",
                "chats_count": chat_count,
                "db_type": "mongodb",
            }

        return self.execute(operation)
