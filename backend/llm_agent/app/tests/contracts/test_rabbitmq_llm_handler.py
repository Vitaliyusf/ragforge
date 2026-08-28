"""Tests for RabbitMQ typed LLM reply and stream contracts."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import os
import unittest

from app.core.config import Settings
from app.messaging.handlers import LLMHandler
from app.llm.interfaces import LLMGenerationResult, LLMUsage
from app.services.llm_service import LLMService
from shared.context import bound_context

from app.tests._service_harness import FakeLLMClient, FakeLogger


class FakeRabbitMQProducer:
    """Capture asynchronous exchange publications for handler tests."""

    def __init__(self):
        self.messages = []

    async def publish(self, routing_key, message):
        self.messages.append((routing_key, message))

    async def reply(self, reply_to, correlation_id, message):
        self.messages.append((reply_to, message))

    def is_connected(self):
        return True


class ThreadedTokenLLMClient:
    """Mirror vLLM's nested worker-thread token callback behavior."""

    def generate(self, invocation):
        def run():
            invocation.on_token("Threaded ", 0)
            invocation.on_token("tokens", 1)

        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(run).result()
        return LLMGenerationResult(
            raw_output="Threaded tokens",
            usage=LLMUsage(provider="fake"),
        )

    def list_models(self):
        return ["test-model"]

    def is_available(self):
        return True


def _settings():
    return Settings(
        default_model="test-model",
        rag_chat_model="test-model",
        llm_implementation="vllm",
    )


def _answer_request():
    return {
        "message_id": "msg-1",
        "message_type": "command",
        "action": "answer_generation",
        "source_service": "rag",
        "target_service": "llm_agent",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "reply_to": "amq.reply.test",
        "stream_to": "rag.stream.test",
        "timestamp": 1730000000000,
        "payload": {
            "request_type": "answer_generation",
            "input": {
                "question": "What is the answer?",
                "retrieved_context": ["Trusted source"],
            },
            "metadata": {"tenant_id": "tenant-1"},
            "debug": {"include_visible_reasoning_steps": True},
        },
    }


class RabbitMQLLMHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def _process(self, handler, body):
        loop = asyncio.get_running_loop()
        context = copy_context()
        return await loop.run_in_executor(
            None,
            context.run,
            handler.process_request_with_reply,
            body,
            body.get("reply_to", "amq.reply.test"),
            body.get("correlation_id", "corr-1"),
            loop,
        )

    async def test_handler_publishes_stream_and_returns_reply(self):
        producer = FakeRabbitMQProducer()
        service = LLMService(FakeLLMClient(), FakeLogger(), _settings())
        handler = LLMHandler(producer, service, FakeLogger(), _settings())

        reply = await self._process(handler, _answer_request())

        stream_messages = [
            message for routing_key, message in producer.messages
            if routing_key == "rag.stream.test"
        ]
        self.assertEqual(len(stream_messages), 3)
        self.assertEqual(stream_messages[0]["message_type"], "stream_event")
        self.assertEqual(stream_messages[0]["payload"]["event_type"], "llm.token")
        self.assertEqual(stream_messages[-1]["payload"]["event_type"], "llm.done")
        self.assertEqual(reply["message_type"], "reply")
        self.assertTrue(reply["success"])
        self.assertEqual(reply["payload"]["request_type"], "answer_generation")

    async def test_handler_returns_normalized_validation_error_reply(self):
        producer = FakeRabbitMQProducer()
        service = LLMService(FakeLLMClient(), FakeLogger(), _settings())
        handler = LLMHandler(producer, service, FakeLogger(), _settings())
        request = _answer_request()
        request["payload"]["input"] = {}

        reply = await self._process(handler, request)

        self.assertEqual(reply["message_type"], "reply")
        self.assertFalse(reply["success"])
        self.assertEqual(reply["payload"]["status"], "error")
        self.assertEqual(reply["error"]["code"], "invalid_request")

    async def test_nested_provider_thread_tokens_are_published(self):
        producer = FakeRabbitMQProducer()
        service = LLMService(ThreadedTokenLLMClient(), FakeLogger(), _settings())
        handler = LLMHandler(producer, service, FakeLogger(), _settings())

        previous_required = os.environ.get("INTERNAL_AUTH_REQUIRED")
        previous_secret = os.environ.get("INTERNAL_AUTH_SECRET")
        os.environ["INTERNAL_AUTH_REQUIRED"] = "true"
        os.environ["INTERNAL_AUTH_SECRET"] = "llm-handler-test-secret-with-32-bytes"
        try:
            with bound_context(tenant_id="tenant-1", user_id="user-1", role="user"):
                reply = await self._process(handler, _answer_request())
        finally:
            if previous_required is None:
                os.environ.pop("INTERNAL_AUTH_REQUIRED", None)
            else:
                os.environ["INTERNAL_AUTH_REQUIRED"] = previous_required
            if previous_secret is None:
                os.environ.pop("INTERNAL_AUTH_SECRET", None)
            else:
                os.environ["INTERNAL_AUTH_SECRET"] = previous_secret

        event_types = [
            message["payload"]["event_type"]
            for routing_key, message in producer.messages
            if routing_key == "rag.stream.test"
        ]
        self.assertEqual(event_types, ["llm.token", "llm.token", "llm.done"])
        self.assertTrue(all(message.get("auth_context") for _, message in producer.messages))
        self.assertTrue(reply["success"])
