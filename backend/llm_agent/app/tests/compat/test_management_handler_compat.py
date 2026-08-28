"""Compatibility tests for legacy management handlers under typed gateway envelopes."""
import unittest

from app.core.config import Settings
from app.core.errors import NotFoundException
from app.messaging.handlers import (
    ConfigManagementHandler,
    ModelHandler,
    ModelManagementHandler,
)

from app.tests._service_harness import FakeLogger


class FakeProducer:
    """Capture handler publications for assertions."""

    def __init__(self):
        self.messages = []
        self.flush_count = 0

    def send(self, topic, message):
        self.messages.append((topic, message))

    def flush(self):
        self.flush_count += 1

    def is_connected(self):
        return True


class FakeModelService:
    """Minimal model service stub for management-lane tests."""

    def __init__(self):
        self.calls = []

    def list_models(self):
        self.calls.append(("list_models",))
        return {"models": [{"name": "demo"}]}

    def list_implementations(self):
        self.calls.append(("list_implementations",))
        return {"implementations": [{"name": "vllm"}], "current": "vllm"}

    def get_implementation_info(self, implementation):
        self.calls.append(("get_implementation_info", implementation))
        if implementation == "missing":
            raise NotFoundException(f"Unknown implementation: {implementation}")
        return {"name": implementation, "description": "demo"}


class FakeConfigService:
    """Minimal config service stub for config-lane tests."""

    def __init__(self):
        self.calls = []

    def get_config(self):
        self.calls.append(("get_config",))
        return {"llm_implementation": "vllm"}


def _settings():
    return Settings(
        llm_implementation="vllm",
        default_model="demo",
        rag_chat_model="demo",
    )


def _typed_request(action, **payload):
    return {
        "message_id": "msg-1",
        "message_type": "query",
        "action": action,
        "source_service": "gateway",
        "target_service": "model_management",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "reply_to": "gateway.replies",
        "timestamp": 1730000000000,
        "payload": payload,
    }


class ManagementHandlerCompatibilityTests(unittest.TestCase):
    """Verify typed gateway envelopes work on legacy correlated handler lanes."""

    def test_model_handler_publishes_typed_reply_for_gateway_request(self):
        producer = FakeProducer()
        service = FakeModelService()
        handler = ModelHandler(producer, service, FakeLogger(), _settings())

        handler.handle(_typed_request("fetch_models"))

        topic, reply = producer.messages[-1]
        self.assertEqual(topic, "gateway.replies")
        self.assertEqual(reply["message_type"], "reply")
        self.assertEqual(reply["action"], "fetch_models")
        self.assertTrue(reply["success"])
        self.assertEqual(reply["payload"]["models"][0]["name"], "demo")
        self.assertEqual(service.calls, [("list_models",)])

    def test_model_management_handler_reads_parameters_from_typed_payload(self):
        producer = FakeProducer()
        service = FakeModelService()
        handler = ModelManagementHandler(producer, service, FakeLogger(), _settings())

        handler.handle(_typed_request("get_implementation_info", implementation="vllm"))

        topic, reply = producer.messages[-1]
        self.assertEqual(topic, "gateway.replies")
        self.assertEqual(reply["message_type"], "reply")
        self.assertEqual(reply["payload"]["name"], "vllm")
        self.assertEqual(service.calls, [("get_implementation_info", "vllm")])

    def test_model_management_handler_includes_status_metadata_on_typed_error(self):
        producer = FakeProducer()
        service = FakeModelService()
        handler = ModelManagementHandler(producer, service, FakeLogger(), _settings())

        handler.handle(_typed_request("get_implementation_info", implementation="missing"))

        topic, reply = producer.messages[-1]
        self.assertEqual(topic, "gateway.replies")
        self.assertFalse(reply["success"])
        self.assertEqual(reply["error"]["status_code"], 404)
        self.assertEqual(reply["error"]["code"], "not_found")

    def test_config_management_handler_rejects_retired_runtime_switch(self):
        producer = FakeProducer()
        service = FakeConfigService()
        handler = ConfigManagementHandler(producer, service, FakeLogger(), _settings())

        handler.handle(_typed_request("switch_implementation", implementation="ollama"))

        topic, reply = producer.messages[-1]
        self.assertEqual(topic, "gateway.replies")
        self.assertEqual(reply["message_type"], "reply")
        self.assertFalse(reply["success"])
        self.assertEqual(reply["error"]["code"], "invalid_request")
        self.assertEqual(reply["error"]["status_code"], 400)
        self.assertIn("get_config", reply["error"]["message"])
        self.assertEqual(service.calls, [])

    def test_model_management_handler_returns_legacy_shape_through_rpc_capture(self):
        producer = FakeProducer()
        service = FakeModelService()
        handler = ModelManagementHandler(producer, service, FakeLogger(), _settings())

        reply = handler.process_request_with_reply(
            {"action": "list_implementations"},
            reply_to="rpc.reply.queue",
            correlation_id="legacy-1",
        )

        self.assertEqual(reply["correlation_id"], "legacy-1")
        self.assertEqual(reply["data"]["implementations"][0]["name"], "vllm")
        self.assertEqual(service.calls, [("list_implementations",)])
        self.assertEqual(producer.messages, [])
