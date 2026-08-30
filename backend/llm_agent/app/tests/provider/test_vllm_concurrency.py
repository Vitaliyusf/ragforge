"""Focused contracts for shared vLLM capacity and transport ownership."""
from __future__ import annotations

import asyncio
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.llm.implementations.vllm import VLLMClient
from app.llm.interfaces import (
    LLMInvocation,
    ProviderOverloadedError,
    ProviderTimeoutError,
)
from app.llm.provider_capacity import ProviderCapacity
from shared.context import bound_context


ACTIONS = (
    "answer_generation",
    "answer_evaluation",
    "content_risk_scan",
    "query_rewrite",
    "memory_extraction",
    "chat_title",
    "chat_summary",
    "memory_curation",
    "metadata",
    "suggested_questions",
)
_ASSERTIONS = unittest.TestCase()


def _config(limit: int = 2, admission_timeout: float = 0.5):
    return SimpleNamespace(
        service_name="llm_agent",
        vllm_base_url="http://vllm:8000",
        vllm_api_key="token",
        max_concurrent_requests=limit,
        provider_admission_timeout_seconds=admission_timeout,
        vllm_max_tokens=16,
        vllm_temperature=0.0,
        vllm_top_p=0.9,
        vllm_top_k=20,
        vllm_connect_timeout=0.1,
        vllm_read_timeout=0.2,
        vllm_write_timeout=0.1,
        vllm_pool_timeout=0.1,
        vllm_keepalive_expiry=30.0,
    )


def _invocation(action: str = "answer_generation") -> LLMInvocation:
    return LLMInvocation(
        system_prompt="system",
        raw_prompt="prompt",
        model="model-a",
        timeout=0.2,
        metadata={"request_type": action},
    )


def _response() -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"text": "ok", "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return response


class BlockingTransport:
    def __init__(self, expected_active: int):
        self.expected_active = expected_active
        self.release = threading.Event()
        self.reached = threading.Event()
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.closed = False

    def post(self, *_args, **_kwargs):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if self.active == self.expected_active:
                self.reached.set()
        self.release.wait(1.0)
        with self.lock:
            self.active -= 1
        return _response()

    def close(self):
        self.closed = True


def test_all_llm_request_classes_share_one_global_bound():
    transport = BlockingTransport(expected_active=2)
    client = VLLMClient(_config(limit=2), http_client=transport)

    def generate(index: int):
        traffic = "eval" if index % 2 else "live"
        with bound_context(traffic_class=traffic):
            return client.generate(_invocation(ACTIONS[index]))

    with ThreadPoolExecutor(max_workers=len(ACTIONS)) as executor:
        futures = [executor.submit(generate, index) for index in range(len(ACTIONS))]
        assert transport.reached.wait(0.5)
        time.sleep(0.05)
        assert transport.max_active == 2
        assert client._capacity.snapshot().inflight == 2
        transport.release.set()
        assert all(future.result().raw_output == "ok" for future in futures)


def test_live_and_background_each_make_progress_under_contention():
    capacity = ProviderCapacity(service="llm_agent", limit=2, admission_timeout=0.5)
    eval_entered = threading.Event()
    release_eval = threading.Event()
    second_eval_entered = threading.Event()
    live_entered = threading.Event()

    def hold_eval(entered: threading.Event):
        with bound_context(traffic_class="eval"):
            with capacity.admit():
                entered.set()
                release_eval.wait(1.0)

    first = threading.Thread(target=hold_eval, args=(eval_entered,))
    second = threading.Thread(target=hold_eval, args=(second_eval_entered,))
    first.start()
    assert eval_entered.wait(0.5)
    second.start()
    time.sleep(0.03)

    def run_live():
        with bound_context(traffic_class="live"):
            with capacity.admit():
                live_entered.set()

    live = threading.Thread(target=run_live)
    live.start()
    assert live_entered.wait(0.5), "eval must leave the reserved live slot available"
    assert not second_eval_entered.is_set()
    release_eval.set()
    assert second_eval_entered.wait(0.5), "background must resume when capacity opens"
    first.join(1.0)
    second.join(1.0)
    live.join(1.0)


def test_cancellation_and_timeout_release_provider_capacity():
    capacity = ProviderCapacity(service="llm_agent", limit=1, admission_timeout=0.1)
    with _ASSERTIONS.assertRaises(asyncio.CancelledError):
        with capacity.admit():
            raise asyncio.CancelledError
    assert capacity.snapshot().inflight == 0

    transport = Mock()
    transport.post.side_effect = httpx.ReadTimeout("model read timed out")
    client = VLLMClient(_config(limit=1), http_client=transport)
    with _ASSERTIONS.assertRaises(ProviderTimeoutError):
        client.generate(_invocation())
    assert client._capacity.snapshot().inflight == 0


def test_admission_and_http_pool_timeouts_are_typed_overload():
    capacity = ProviderCapacity(service="llm_agent", limit=1, admission_timeout=0.03)
    release = threading.Event()
    entered = threading.Event()

    def hold():
        with capacity.admit():
            entered.set()
            release.wait(1.0)

    thread = threading.Thread(target=hold)
    thread.start()
    assert entered.wait(0.5)
    with _ASSERTIONS.assertRaisesRegex(
        ProviderOverloadedError, "admission timed out"
    ):
        with capacity.admit():
            pass
    release.set()
    thread.join(1.0)

    transport = Mock()
    transport.post.side_effect = httpx.PoolTimeout("pool timed out")
    client = VLLMClient(_config(limit=1), http_client=transport)
    with _ASSERTIONS.assertRaisesRegex(ProviderOverloadedError, "pool is saturated"):
        client.generate(_invocation())
    assert client._capacity.snapshot().inflight == 0


def test_one_reused_client_has_explicit_pool_limits_and_shutdown():
    transport = Mock()
    transport.post.return_value = _response()
    client_factory = Mock(return_value=transport)
    with patch("app.llm.implementations.vllm.httpx.Client", client_factory):
        client = VLLMClient(_config(limit=2))
        client.generate(_invocation("answer_generation"))
        client.generate(_invocation("metadata"))

    client_factory.assert_called_once()
    limits = client_factory.call_args.kwargs["limits"]
    assert limits.max_connections == 2
    assert limits.max_keepalive_connections == 2
    assert transport.post.call_count == 2
    assert not hasattr(client, "_executor")

    client.shutdown()
    transport.close.assert_called_once_with()
    assert client._capacity.snapshot().closed is True
    with _ASSERTIONS.assertRaisesRegex(ProviderOverloadedError, "shutting down"):
        client.generate(_invocation())


def test_client_limit_cannot_silently_exceed_vllm_sequence_capacity():
    with _ASSERTIONS.assertRaisesRegex(
        ValidationError, "must not exceed vllm_max_num_seqs"
    ):
        Settings(max_concurrent_requests=5, vllm_max_num_seqs=4)


def load_tests(_loader, _tests, _pattern):
    """Let the stdlib runner execute these focused tests when pytest is blocked."""
    functions = (
        test_all_llm_request_classes_share_one_global_bound,
        test_live_and_background_each_make_progress_under_contention,
        test_cancellation_and_timeout_release_provider_capacity,
        test_admission_and_http_pool_timeouts_are_typed_overload,
        test_one_reused_client_has_explicit_pool_limits_and_shutdown,
        test_client_limit_cannot_silently_exceed_vllm_sequence_capacity,
    )
    return unittest.TestSuite(unittest.FunctionTestCase(function) for function in functions)
