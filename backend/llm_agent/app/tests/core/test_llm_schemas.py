"""Tests for shared-envelope typed LLM request validation."""
import unittest

from pydantic import ValidationError

from app.schemas.llm import MemoryCurationAction, MemoryItem, validate_model_execution_request_message


def _base_message():
    return {
        "message_id": "msg-1",
        "message_type": "command",
        "source_service": "gateway",
        "target_service": "llm_agent",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "reply_to": "gateway.replies",
        "timestamp": 1730000000000,
    }


class ModelExecutionSchemaTests(unittest.TestCase):
    """Validate shared-envelope typed request messages."""

    def test_request_validation_by_request_type(self):
        cases = [
            (
                "answer_generation",
                {
                    "question": "What is the answer?",
                    "retrieved_context": ["Context 1", "Context 2"],
                },
            ),
            (
                "answer_evaluation",
                {
                    "question": "What is the answer?",
                    "answer": "The answer is 42.",
                    "reference_context": "Trusted source",
                },
            ),
            (
                "content_risk_scan",
                {
                    "content": "Some content",
                    "policy_hints": ["violence"],
                },
            ),
            (
                "query_rewrite",
                {
                    "query": "best cpu for embeddings",
                },
            ),
            (
                "memory_extraction",
                {
                    "conversation_history": [
                        {"role": "user", "content": "I prefer concise summaries."}
                    ]
                },
            ),
            ("chat_title", {"conversation_history": []}),
            ("chat_summary", {"conversation_history": []}),
            (
                "memory_curation",
                {"conversation_history": [], "existing_memory": []},
            ),
        ]

        for request_type, input_payload in cases:
            with self.subTest(request_type=request_type):
                message = _base_message()
                message["action"] = request_type
                message["payload"] = {
                    "request_type": request_type,
                    "input": input_payload,
                    "metadata": {"tenant_id": "tenant-1"},
                    "debug": {"include_visible_reasoning_steps": True},
                }

                request = validate_model_execution_request_message(message)

                self.assertEqual(request.payload.request_type, request_type)
                self.assertEqual(request.request_id, "req-1")

    def test_signed_transport_auth_context_is_accepted(self):
        message = _base_message()
        message["action"] = "answer_generation"
        message["auth_context"] = "signed-ticket"
        message["payload"] = {
            "request_type": "answer_generation",
            "input": {"question": "Hello", "retrieved_context": []},
            "metadata": {},
        }

        request = validate_model_execution_request_message(message)

        self.assertEqual(request.auth_context, "signed-ticket")

    def test_invalid_request_type_is_rejected(self):
        message = _base_message()
        message["action"] = "unknown"
        message["payload"] = {
            "request_type": "unknown",
            "input": {},
            "metadata": {},
        }

        with self.assertRaises(ValidationError):
            validate_model_execution_request_message(message)

    def test_missing_required_input_field_is_rejected(self):
        message = _base_message()
        message["action"] = "answer_evaluation"
        message["payload"] = {
            "request_type": "answer_evaluation",
            "input": {"question": "What is the answer?"},
            "metadata": {},
        }

        with self.assertRaises(ValidationError):
            validate_model_execution_request_message(message)

    def test_flat_legacy_shape_is_rejected(self):
        legacy_payload = {
            "request_type": "answer_generation",
            "input": {"question": "What is the answer?", "retrieved_context": "Trusted source"},
            "metadata": {},
            "request_id": "req-1",
            "trace_id": "trace-1",
            "correlation_id": "corr-1",
            "reply_to": "gateway.replies",
        }

        with self.assertRaises(ValidationError):
            validate_model_execution_request_message(legacy_payload)


class MemoryAgentOutputSchemaTests(unittest.TestCase):
    def test_candidate_extraction_rejects_unbounded_or_untyped_values(self):
        with self.assertRaises(ValidationError):
            MemoryItem(type="preference", content="ok", confidence="high", action="create")
        with self.assertRaises(ValidationError):
            MemoryItem(type="guess", content="A durable fact", confidence=0.8, action="create")

    def test_lifecycle_actions_enforce_action_specific_fields(self):
        with self.assertRaises(ValidationError):
            MemoryCurationAction(action="create", memory_id="existing", content="New fact")
        with self.assertRaises(ValidationError):
            MemoryCurationAction(action="supersede", content="Corrected fact")
        with self.assertRaises(ValidationError):
            MemoryCurationAction(action="delete", memory_id="existing", content="must be absent")

        action = MemoryCurationAction(
            action="update",
            memory_id="existing",
            content="Updated durable fact",
            confidence=0.9,
        )
        self.assertEqual(action.memory_id, "existing")
