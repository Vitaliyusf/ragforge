"""A failed LLM call must still report what the provider already told us.

An `answer_evaluation` reply that says only `structured_output_invalid` cannot
distinguish an output truncated at its token ceiling from one the model
finished normally and the parser rejected. The first is a budget to raise, the
second is not, and raising the ceiling for the second only hides it. These
tests pin the evidence path end to end: llm_agent's reply → the RPC failure →
the graph result → the eval row → the benchmark summary and export.

Everything asserted here is bounded labels and numbers. No prompt, model
output, answer or context text may travel on this path, and the export test
checks that too.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

import pytest

from app.services.benchmark_export import _trace_evidence
from app.services.benchmark_summary import llm_action_summary, summarize_benchmark
from app.services.conversation_events import CollectingConversationEmitter
from app.services.conversation_messages import (
    LLM_EVIDENCE_KEY,
    DownstreamRPCError,
    extract_reply_payload,
)
from app.tests._service_harness import TEST_IDENTITY, build_service
from app.tests.eval._harness import FailingGraph, build, fetch, run_end_to_end
from shared.context import bound_context


def _reply(*, success: bool, payload: Dict[str, Any]) -> Dict[str, Any]:
    reply = {
        "message_id": "m1",
        "message_type": "reply",
        "action": "answer_evaluation",
        "source_service": "llm_agent",
        "target_service": "rag",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "timestamp": 1730000000000,
        "success": success,
        "payload": payload,
    }
    if not success:
        reply["error"] = {
            "code": "structured_output_invalid",
            "message": "Structured output parse failed: No valid JSON object found",
        }
    return reply


def _truncated_payload() -> Dict[str, Any]:
    return {
        "request_type": "answer_evaluation",
        "status": "error",
        "raw_prompt": "",
        "system_prompt": "",
        "visible_reasoning_steps": [],
        "raw_output": "",
        "usage": {
            "provider": "vllm",
            "input_tokens": 1804,
            "output_tokens": 512,
            "total_tokens": 2316,
        },
        "provider_finish_reason": "length",
        "application_status": "structured_output_invalid",
        "parse_stage": "parse",
        "max_tokens": 512,
        "latency_ms": 4200,
        "model": "qwen",
        "prompt_version": "answer_evaluation.v1",
        "trace": {"trace_id": "trace-1"},
        "errors": [{"code": "structured_output_invalid", "message": "parse failed"}],
    }


# ── The failed reply keeps its evidence ───────────────────────────────────


def test_failed_evaluator_reply_keeps_finish_reason_and_output_tokens():
    with pytest.raises(DownstreamRPCError) as raised:
        extract_reply_payload(_reply(success=False, payload=_truncated_payload()))

    evidence = raised.value.evidence
    assert evidence["provider_finish_reason"] == "length"
    assert evidence["application_status"] == "structured_output_invalid"
    assert evidence["parse_stage"] == "parse"
    # 512 output tokens against a 512 ceiling: the truncation evidence itself.
    assert evidence["output_tokens"] == 512
    assert evidence["max_tokens"] == 512
    assert evidence["input_tokens"] == 1804


def test_successful_reply_attaches_bounded_evidence():
    payload = {
        **_truncated_payload(),
        "status": "success",
        "provider_finish_reason": "stop",
        "application_status": "success",
        "parse_stage": None,
        "errors": [],
        "parsed_output": {"verdict": "pass", "issues": []},
    }

    normalized = extract_reply_payload(_reply(success=True, payload=payload))

    evidence = normalized[LLM_EVIDENCE_KEY]
    assert evidence["provider_finish_reason"] == "stop"
    assert evidence["application_status"] == "success"
    assert "parse_stage" not in evidence


def test_reply_from_an_older_llm_agent_is_still_readable():
    """A reply written before the split contract reports what it does know."""
    payload = _truncated_payload()
    for field in ("provider_finish_reason", "application_status", "parse_stage", "max_tokens"):
        payload.pop(field)

    with pytest.raises(DownstreamRPCError) as raised:
        extract_reply_payload(_reply(success=False, payload=payload))

    evidence = raised.value.evidence
    # No provider finish reason was reported, and none is invented.
    assert evidence["provider_finish_reason"] == "unknown"
    # The status still comes from the error code the old contract carried.
    assert evidence["application_status"] == "structured_output_invalid"
    assert evidence["parse_stage"] == "unknown"
    assert evidence["max_tokens"] is None
    assert evidence["output_tokens"] == 512


def test_unbounded_provider_values_are_normalized():
    payload = {
        **_truncated_payload(),
        "provider_finish_reason": "some-new-vllm-reason",
        "application_status": "something the provider made up",
        "parse_stage": "elsewhere",
        "usage": {"provider": "vllm"},
    }

    with pytest.raises(DownstreamRPCError) as raised:
        extract_reply_payload(_reply(success=False, payload=payload))

    evidence = raised.value.evidence
    assert evidence["provider_finish_reason"] == "other"
    assert evidence["application_status"] == "unknown"
    assert evidence["parse_stage"] == "unknown"
    # Usage the provider never reported stays unmeasured rather than zero.
    assert evidence["output_tokens"] is None


# ── The graph carries the evidence out with the failure ───────────────────


@pytest.fixture(autouse=True)
def authenticated_request_context():
    with bound_context(**TEST_IDENTITY.to_dict()):
        yield


def _run_turn(question: str, backend_patch=None):
    service, backend, _ = build_service()
    if backend_patch is not None:
        backend_patch(backend)
    request = service.build_request({"question": question, "mode": "regular"})
    emitter = CollectingConversationEmitter(request)
    return asyncio.run(service.graph_runner.run(request, emitter))


def test_a_failed_evaluator_call_reports_its_evidence_on_the_result():
    def fail_evaluation(backend):
        async def evaluate_answer(request, answer, retrieved_chunks, mode):
            raise DownstreamRPCError(
                "structured_output_invalid",
                "Structured output parse failed",
                {
                    "request_type": "answer_evaluation",
                    "provider_finish_reason": "length",
                    "application_status": "structured_output_invalid",
                    "parse_stage": "parse",
                    "input_tokens": 1804,
                    "output_tokens": 512,
                    "total_tokens": 2316,
                    "max_tokens": 512,
                    "latency_ms": 4200,
                },
            )

        backend.evaluate_answer = evaluate_answer

    result = _run_turn("Break evaluation", fail_evaluation)

    assert result["outcome"] == "failed"
    assert result["failed_node"] == "evaluate_answer_light"
    assert result["error_class"] == "DownstreamRPCError"
    evaluation = [
        action
        for action in result["llm_actions"]
        if action["request_type"] == "answer_evaluation"
    ]
    assert evaluation == [
        {
            "request_type": "answer_evaluation",
            "provider_finish_reason": "length",
            "application_status": "structured_output_invalid",
            "parse_stage": "parse",
            "input_tokens": 1804,
            "output_tokens": 512,
            "total_tokens": 2316,
            "max_tokens": 512,
            "latency_ms": 4200,
        }
    ]


def test_a_successful_turn_records_the_calls_it_made():
    def annotate(backend):
        original = backend.evaluate_answer

        async def evaluate_answer(request, answer, retrieved_chunks, mode):
            response = await original(request, answer, retrieved_chunks, mode)
            return {
                **response,
                LLM_EVIDENCE_KEY: {
                    "request_type": "answer_evaluation",
                    "provider_finish_reason": "stop",
                    "application_status": "success",
                    "input_tokens": 1804,
                    "output_tokens": 260,
                    "total_tokens": 2064,
                    "max_tokens": 512,
                    "latency_ms": 2100,
                },
            }

        backend.evaluate_answer = evaluate_answer

    result = _run_turn("What is RAG?", annotate)

    assert result["outcome"] == "success"
    assert [action["request_type"] for action in result["llm_actions"]] == [
        "answer_evaluation"
    ]
    assert result["llm_actions"][0]["output_tokens"] == 260


# ── The benchmark summary and export ──────────────────────────────────────


def _rows():
    return [
        {
            "item_id": "one",
            "latency_ms": 100,
            "llm_actions": [
                {
                    "request_type": "answer_evaluation",
                    "provider_finish_reason": "length",
                    "application_status": "structured_output_invalid",
                    "parse_stage": "parse",
                    "output_tokens": 512,
                    "max_tokens": 512,
                },
                {
                    "request_type": "answer_generation",
                    "provider_finish_reason": "stop",
                    "application_status": "success",
                    "output_tokens": 96,
                },
            ],
        },
        {
            "item_id": "two",
            "latency_ms": 120,
            "llm_actions": [
                {
                    "request_type": "answer_evaluation",
                    "provider_finish_reason": "stop",
                    "application_status": "success",
                    "output_tokens": 260,
                    "max_tokens": 512,
                }
            ],
        },
    ]


def test_summary_counts_failures_and_their_provider_finish_reasons():
    summary = llm_action_summary(_rows())

    assert summary["llm_action_failures"]["answer_evaluation"]["total"] == 1
    assert (
        summary["llm_action_failures"]["answer_evaluation"]["structured_output_invalid"]
        == 1
    )
    assert summary["llm_action_failures"]["answer_evaluation"]["timeout"] == 0
    # Only the failed evaluator calls are counted here.
    assert summary["answer_evaluation_failure_finish_reasons"]["length"] == 1
    assert summary["answer_evaluation_failure_finish_reasons"]["stop"] == 0
    assert "answer_generation" not in summary["llm_action_failures"]
    assert summary["calls"] == {"answer_evaluation": 2, "answer_generation": 1}
    # The failed call's output tokens are part of the distribution: they are
    # what says the failures sat at the ceiling.
    assert summary["output_tokens"]["answer_evaluation"]["max"] == 512
    assert summary["output_tokens"]["answer_evaluation"]["sample_count"] == 2


def test_rows_without_llm_evidence_summarize_to_empty_not_to_zeros():
    summary = llm_action_summary([{"item_id": "one", "latency_ms": 5}])

    assert summary["calls"] == {}
    assert summary["llm_action_failures"] == {}
    assert summary["output_tokens"] == {}


def test_benchmark_summary_stays_strict_json():
    document = {
        "benchmark_id": "b1",
        "phases": [{"name": "end_to_end", "run_id": "r1", "results": {}}],
    }
    summary = summarize_benchmark(
        document, runs=[{"run_id": "r1", "per_item": _rows()}]
    )

    phase = summary["phases"][0]
    assert phase["llm_actions"]["answer_evaluation_failure_finish_reasons"]["length"] == 1
    assert summary["totals"]["llm_actions"]["calls"]["answer_evaluation"] == 2
    # allow_nan=False is the whole contract: no NaN or Infinity may reach a ZIP.
    json.dumps(summary, allow_nan=False)


def test_export_keeps_llm_evidence_and_no_model_text():
    rows = _rows()
    rows[0]["answer"] = "the answer text"
    rows[0]["query"] = "the question text"

    exported = _trace_evidence(rows)

    assert exported[0]["llm_actions"][0]["provider_finish_reason"] == "length"
    assert exported[0]["llm_actions"][0]["output_tokens"] == 512
    assert "answer" not in exported[0]
    assert "query" not in exported[0]



def test_a_failed_item_row_keeps_the_evaluator_evidence():
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c1"]}]
    )
    runner.graph_runner = FailingGraph(
        {
            "outcome": "failed",
            "error": "structured_output_invalid: Structured output parse failed",
            "error_class": "DownstreamRPCError",
            "failed_node": "evaluate_answer_light",
            "answer": "",
            "sources": [{"chunk_id": "c1"}],
            "llm_actions": [
                {
                    "request_type": "answer_evaluation",
                    "provider_finish_reason": "length",
                    "application_status": "structured_output_invalid",
                    "parse_stage": "parse",
                    "output_tokens": 512,
                    "max_tokens": 512,
                }
            ],
        },
        context=[{"chunk_id": "c1"}],
    )

    run = run_end_to_end(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]

    # GEN-03B's invariants still hold, and the new evidence rides with them.
    assert row["outcome"] == "failed"
    assert row["failed_node"] == "evaluate_answer_light"
    assert row["retrieved_ids"] == ["c1"]
    assert row["llm_actions"][0]["provider_finish_reason"] == "length"
    assert row["llm_actions"][0]["output_tokens"] == 512
