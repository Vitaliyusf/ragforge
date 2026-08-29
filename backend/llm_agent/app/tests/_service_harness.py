"""Shared fakes and builders for `LLMService` tests.

Cross-domain on purpose: budget, structured-output, streaming, observability
and legacy management-handler tests all drive the real service against these
fakes instead of reimplementing a provider client.
"""
from __future__ import annotations

from app.core.config import Settings
from app.llm.interfaces import ILLMClient, LLMGenerationResult, LLMInvocation, LLMUsage
from app.schemas.llm import validate_model_execution_request_message

# Typed actions, in the order the settings/env tests assert on.
ACTION_ORDER = (
    "answer_generation",
    "answer_evaluation",
    "content_risk_scan",
    "query_rewrite",
    "memory_extraction",
    "chat_title",
    "chat_summary",
    "memory_curation",
)

# Valid structured payloads per action, reused by tests that only care that a
# request completes rather than about the payload itself.
VALID_RESPONSES = {
    "answer_generation": "A supported answer.",
    "answer_evaluation": (
        '{"verdict":"pass","groundedness_score":1,"completeness_score":1,'
        '"safety_score":1,"issues":[],"claims":[],"unsupported_claim_count":0,'
        '"hallucination_verdict":"none","revision_applied":false}'
    ),
    "content_risk_scan": '{"risk_level":"low","categories":[],"flags":[],"summary":"safe"}',
    "query_rewrite": '{"rewritten_query":"widgets","search_intent":"lookup"}',
    "memory_extraction": '{"memories":[]}',
    "chat_title": '{"title":"Beta launch"}',
    "chat_summary": '{"summary":"The beta launched."}',
    "memory_curation": '{"actions":[],"summary":"No changes"}',
}

VALID_INPUTS = {
    "answer_generation": {"question": "Q?", "retrieved_context": "Context"},
    "answer_evaluation": {
        "question": "Q?",
        "answer": "A.",
        "reference_context": "Context",
    },
    "content_risk_scan": {"content": "safe", "policy_hints": []},
    "query_rewrite": {"query": "widgets"},
    "memory_extraction": {"conversation_history": []},
    "chat_title": {"conversation_history": []},
    "chat_summary": {"conversation_history": []},
    "memory_curation": {"conversation_history": [], "existing_memory": []},
}

EVALUATION_INPUT = {
    "question": "What is the answer?",
    "answer": "The answer is 42.",
    "reference_context": "Trusted source",
}

RISK_SCAN_INPUT = {
    "content": "A short harmless sentence.",
    "policy_hints": ["violence"],
}

GENERATION_INPUT = {
    "question": "What is the answer?",
    "retrieved_context": "Trusted source",
}


class FakeLogger:
    """Simple in-memory logger for service tests."""

    def __init__(self):
        self.entries = []

    def log(self, location, message, data=None, hypothesis_id="A"):
        self.entries.append(
            {
                "location": location,
                "message": message,
                "data": data or {},
                "hypothesis_id": hypothesis_id,
            }
        )


class FakeLLMClient(ILLMClient):
    """Configurable fake client for reply and streaming tests."""

    def __init__(self, responses=None, exception=None, usage=None, finish_reason="completed"):
        self.responses = responses or {}
        self.exception = exception
        self.finish_reason = finish_reason
        self.usage = usage or LLMUsage(
            provider="fake",
            input_tokens=5,
            output_tokens=3,
            total_tokens=8,
        )
        self.invocations = []

    def generate(self, invocation: LLMInvocation) -> LLMGenerationResult:
        self.invocations.append(invocation)
        if self.exception is not None:
            raise self.exception

        request_type = invocation.metadata.get("request_type")
        raw_output = self.responses.get(request_type, "default response")

        if invocation.on_token is not None:
            chunks = ["Hello", " world"]
            for index, token in enumerate(chunks):
                invocation.on_token(token, index)
            raw_output = "".join(chunks)

        return LLMGenerationResult(
            raw_output=raw_output,
            usage=self.usage,
            finish_reason=self.finish_reason,
        )

    def list_models(self) -> list:
        return ["test-model"]

    def is_available(self) -> bool:
        return True


class DummySpan:
    """Minimal span for fake tracing."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def finish(self, outputs=None, error=None):
        return None


class DummyTrace:
    """Capture metadata added during a request."""

    def __init__(self, metadata):
        self.metadata = dict(metadata)

    def span(self, name, inputs=None, metadata=None):
        if metadata:
            self.metadata.update(metadata)
        return DummySpan()

    def add_metadata(self, metadata):
        self.metadata.update(metadata)

    def finish(self, outputs=None, error=None):
        return None

    def snapshot(self):
        return type(
            "Snapshot",
            (),
            {
                "trace_id": self.metadata.get("trace_id", ""),
                "langsmith_run_id": None,
                "langsmith_trace_url": None,
            },
        )()


class DummyTracer:
    """Capture root trace metadata from the service."""

    def __init__(self):
        self.last_trace = None

    def start_execution(self, name, trace_id, inputs, metadata):
        self.last_trace = DummyTrace(metadata)
        return self.last_trace


class RecordingMetric:
    def __init__(self):
        self.label_calls = []
        self.increments = []
        self.observations = []

    def labels(self, **labels):
        self.label_calls.append(labels)
        return self

    def inc(self, value=1):
        self.increments.append(value)

    def observe(self, value):
        self.observations.append(value)


class RecordingMetrics:
    def __init__(self):
        self.llm_requests_total = RecordingMetric()
        self.llm_request_duration = RecordingMetric()
        self.llm_provider_duration = RecordingMetric()
        self.llm_errors_total = RecordingMetric()
        self.llm_tokens_total = RecordingMetric()
        self.llm_output_tokens = RecordingMetric()
        self.llm_finish_reasons_total = RecordingMetric()
        self.llm_provider_finish_reasons_total = RecordingMetric()


def settings(**overrides) -> Settings:
    defaults = {
        "default_model": "test-model",
        "rag_chat_model": "test-model",
        "llm_implementation": "vllm",
        "debug_max_field_length": 48,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def request_message(request_type, input_payload, **overrides):
    payload = {
        "message_id": "msg-1",
        "message_type": "command",
        "action": request_type,
        "source_service": "gateway",
        "target_service": "llm_agent",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "reply_to": "gateway.replies",
        "timestamp": 1730000000000,
        "payload": {
            "request_type": request_type,
            "input": input_payload,
            "metadata": {"tenant_id": "tenant-1"},
            "debug": {"include_visible_reasoning_steps": True},
        },
    }
    payload.update(overrides)
    return validate_model_execution_request_message(payload)
