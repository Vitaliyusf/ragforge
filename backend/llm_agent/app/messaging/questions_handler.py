"""Suggested-questions generator RabbitMQ handler."""
from typing import Any, Dict

from app.messaging.base_handler import BaseRabbitMQHandler
from app.messaging.interfaces import IProducer
from app.core.config import Settings
from app.core.constants import FilesAction
from app.core.logging_config import ServiceLogger
from app.services.llm_service import LLMService

try:
    from shared.schemas.message_schemas import GenerateQuestionsRequest
    _HAS_SCHEMAS = True
except ImportError:
    _HAS_SCHEMAS = False


class GenerateQuestionsHandler(BaseRabbitMQHandler):
    """Generate 1-2 suggested questions per file and push to the files service."""

    def __init__(
        self,
        producer: IProducer,
        llm_service: LLMService,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        super().__init__(producer, logger, config)
        self.llm_service = llm_service

    def handle(self, message: Dict[str, Any]) -> None:
        if _HAS_SCHEMAS:
            validated, error = self._validate(message, GenerateQuestionsRequest)
            if error:
                self.logger.log("rabbitmq:generate_questions", "Schema validation failed, skipping", {"error": error}, hypothesis_id="E")
                return

        file_id = message.get("file_id", "")
        summary = message.get("summary", "")
        filename = message.get("filename", "")

        self.logger.log(
            "rabbitmq:generate_questions",
            "Processing generate-questions request",
            {"file_id": file_id, "summary_length": len(summary)},
        )

        if not summary:
            self.logger.log(
                "rabbitmq:generate_questions",
                "No summary provided, skipping",
                {"file_id": file_id},
                hypothesis_id="W",
            )
            return

        try:
            prompt = (
                f"Based on the following document summary, generate exactly 1 or 2 short, specific "
                f"questions that a user could ask to learn more about this document. Each question should "
                f"be one sentence. Return only the questions, one per line, no numbering or bullets.\n\n"
                f"Document: {filename}\nSummary: {summary[:2000]}\n\nQuestions:"
            )
            response = self.llm_service.generate_text(prompt, self.config.summary_model, self.config.summary_timeout)
            if not response or not response.strip():
                return

            lines = [q.strip() for q in response.strip().split("\n") if q.strip()]
            questions = []
            for line in lines:
                q = line.lstrip("0123456789.-) ").strip()
                if q:
                    questions.append(q if q.endswith("?") else q + "?")
            questions = questions[:2]

            if questions:
                self._fire_and_forget(
                    self.config.files_queue,
                    {"action": FilesAction.UPDATE_SUGGESTED_QUESTIONS, "file_id": file_id, "questions": questions},
                )
                self.logger.log(
                    "rabbitmq:generate_questions",
                    "Suggested questions sent",
                    {"file_id": file_id, "questions_count": len(questions)},
                )
        except Exception as e:
            self.logger.log(
                "rabbitmq:generate_questions",
                "Error generating questions",
                {"file_id": file_id, "error": str(e)},
                hypothesis_id="E",
            )
