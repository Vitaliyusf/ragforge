"""Streaming token-usage regressions for the vLLM adapter."""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.llm.implementations.vllm import VLLMClient
from app.llm.interfaces import LLMInvocation


def _config():
    return SimpleNamespace(
        vllm_base_url="http://vllm:8000",
        vllm_api_key="private-vllm-token",
        max_concurrent_requests=1,
        vllm_max_tokens=128,
        vllm_temperature=0.1,
        vllm_top_p=0.9,
        vllm_top_k=20,
    )


def _invocation(on_token=None, max_tokens=None):
    return LLMInvocation(
        system_prompt="Be concise.",
        raw_prompt="Answer the question.",
        model="model-a",
        on_token=on_token,
        max_tokens=max_tokens,
    )


class _StreamResponse:
    def __init__(self, lines=None, error=None):
        self._lines = lines or []
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def raise_for_status(self):
        return None

    def iter_lines(self):
        for line in self._lines:
            yield line
        if self._error is not None:
            raise self._error


def _sse(payload):
    return f"data: {json.dumps(payload)}"


class VLLMStreamingUsageTests(unittest.TestCase):
    def test_invocation_budget_reaches_vllm_payload(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"text": "ok", "finish_reason": "stop"}]}
        post = Mock(return_value=response)
        client = VLLMClient(_config())

        with patch("app.llm.implementations.vllm.httpx.post", post):
            client._invoke_vllm(_invocation(max_tokens=37))

        self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 37)

    def test_stream_requests_usage_and_preserves_visible_stream(self):
        token_events = []
        stream = Mock(
            return_value=_StreamResponse(
                [
                    _sse({"choices": [{"text": "Hello", "finish_reason": None}]}),
                    _sse({"choices": [{"text": " world", "finish_reason": "stop"}]}),
                    _sse(
                        {
                            "choices": [],
                            "usage": {
                                "prompt_tokens": 11,
                                "completion_tokens": 2,
                                "total_tokens": 13,
                            },
                        }
                    ),
                    "data: [DONE]",
                ]
            )
        )
        client = VLLMClient(_config())

        with patch("app.llm.implementations.vllm.httpx.stream", stream):
            result = client._invoke_vllm(
                _invocation(lambda token, index: token_events.append((token, index)))
            )

        request_payload = stream.call_args.kwargs["json"]
        self.assertTrue(request_payload["stream"])
        self.assertEqual(request_payload["stream_options"], {"include_usage": True})
        self.assertEqual(token_events, [("Hello", 0), (" world", 1)])
        self.assertEqual(result.raw_output, "Hello world")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage.input_tokens, 11)
        self.assertEqual(result.usage.output_tokens, 2)
        self.assertEqual(result.usage.total_tokens, 13)

    def test_stream_without_usage_preserves_missing_values(self):
        stream = Mock(
            return_value=_StreamResponse(
                [
                    _sse({"choices": [{"text": "Hello", "finish_reason": "length"}]}),
                    "data: [DONE]",
                ]
            )
        )
        client = VLLMClient(_config())

        with patch("app.llm.implementations.vllm.httpx.stream", stream):
            result = client._invoke_vllm(_invocation(lambda _token, _index: None))

        self.assertEqual(result.raw_output, "Hello")
        self.assertEqual(result.finish_reason, "length")
        self.assertIsNone(result.usage.input_tokens)
        self.assertIsNone(result.usage.output_tokens)
        self.assertIsNone(result.usage.total_tokens)

    def test_stream_error_before_usage_is_not_masked(self):
        original_error = RuntimeError("stream interrupted")
        stream = Mock(
            return_value=_StreamResponse(
                [_sse({"choices": [{"text": "partial", "finish_reason": None}]})],
                error=original_error,
            )
        )
        client = VLLMClient(_config())

        with patch("app.llm.implementations.vllm.httpx.stream", stream):
            with self.assertRaisesRegex(RuntimeError, "stream interrupted") as context:
                client._invoke_vllm(_invocation(lambda _token, _index: None))

        self.assertIs(context.exception, original_error)

    def test_non_streaming_request_and_usage_contract_are_unchanged(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"text": "Complete", "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 1,
                "total_tokens": 8,
            },
        }
        post = Mock(return_value=response)
        client = VLLMClient(_config())

        with patch("app.llm.implementations.vllm.httpx.post", post):
            result = client._invoke_vllm(_invocation())

        request_payload = post.call_args.kwargs["json"]
        self.assertFalse(request_payload["stream"])
        self.assertNotIn("stream_options", request_payload)
        self.assertEqual(result.raw_output, "Complete")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage.input_tokens, 7)
        self.assertEqual(result.usage.output_tokens, 1)
        self.assertEqual(result.usage.total_tokens, 8)
