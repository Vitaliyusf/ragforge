"""Deterministic safety and lifecycle checks for the Memory Agent boundary."""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from app.agent.memory_agent import (
    AgentScope,
    MemoryAgent,
    MemoryAgentError,
    MemoryAgentLLMError,
    RetryBudgets,
)


def _scope(**changes):
    values = {
        "tenant_id": "tenant-1", "user_id": "user-1", "role": "user",
        "request_id": "req-1", "trace_id": "trace-1", "chat_id": "chat-1",
        "delete_authorized": False,
    }
    values.update(changes)
    return AgentScope(**values)


def _memory(memory_id="memory-1", text="The project uses Python.", **extra):
    value = {
        "id": memory_id, "content": {"text": text},
        "tenant_id": "tenant-1", "owner_id": "user-1",
    }
    value.update(extra)
    return value


def _agent(responses):
    llm = Mock(side_effect=responses)
    memory_service = Mock()
    memory_service.write_memory.return_value = {"status": "accepted", "memory_id": "written-1"}
    memory_service.delete_memory.return_value = {"status": "deleted", "memory_id": "memory-1"}
    agent = MemoryAgent(memory_service, llm, Mock(), retry_budgets=RetryBudgets())
    return agent, memory_service, llm


SCENARIOS = [
    ("durable preference", [{"role": "user", "content": "I prefer concise answers."}], [], [{"action": "create", "content": "User prefers concise answers."}], 1),
    ("transient chatter", [{"role": "user", "content": "Hello for now."}], [], [{"action": "ignore", "reason": "transient"}], 0),
    ("project fact", [{"role": "user", "content": "This project uses Python."}], [], [{"action": "create", "content": "The project uses Python."}], 1),
    ("duplicate fact", [{"role": "user", "content": "This project uses Python."}], [_memory()], [{"action": "ignore", "reason": "duplicate"}], 0),
    ("corrected fact", [{"role": "user", "content": "Correction: it uses Go."}], [_memory()], [{"action": "supersede", "memory_id": "memory-1", "content": "The project uses Go."}], 1),
    ("temporal update", [{"role": "user", "content": "As of today deployment is complete."}], [_memory(text="Deployment is pending.")], [{"action": "update", "memory_id": "memory-1", "content": "Deployment is complete."}], 1),
    ("scope-specific fact", [{"role": "user", "content": "Staging uses SQLite."}], [_memory()], [{"action": "create", "content": "Staging uses SQLite.", "scope": {"environment": "staging"}}], 1),
    ("contradiction", [{"role": "user", "content": "That older claim may be wrong."}], [_memory()], [{"action": "merge_suggestion", "memory_id": "memory-1", "reason": "ambiguous correction"}], 0),
    ("irrelevant assistant output", [{"role": "assistant", "content": "The user probably likes Rust."}], [], [{"action": "ignore", "reason": "assistant inference"}], 0),
    ("Hebrew preference", [{"role": "user", "content": "אני מעדיף תשובות קצרות."}], [], [{"action": "create", "content": "המשתמש מעדיף תשובות קצרות."}], 1),
    ("mixed language fact", [{"role": "user", "content": "הפרויקט uses PostgreSQL in production."}], [], [{"action": "create", "content": "The project uses PostgreSQL in production."}], 1),
]


class MemoryAgentPolicyTests(unittest.TestCase):
    def test_deterministic_agent_scenarios(self):
        for name, history, existing, actions, expected_mutations in SCENARIOS:
            with self.subTest(name=name):
                agent, memory_service, _ = _agent([{"actions": actions, "summary": name}])
                result = agent.curate(history, existing, _scope(), timeout=1.0)
                self.assertEqual(result.status, "success")
                self.assertEqual(len(result.mutations), expected_mutations)
                self.assertEqual(memory_service.delete_memory.call_count, 0)

    def test_delete_requires_explicit_product_authorization_and_is_not_retried(self):
        agent, memory_service, llm = _agent(
            [{"actions": [{"action": "delete", "memory_id": "memory-1"}], "summary": "delete"}]
        )
        result = agent.curate([], [_memory()], _scope(delete_authorized=False), timeout=1.0)
        self.assertEqual(result.status, "fallback")
        self.assertEqual(llm.call_count, 1)
        memory_service.delete_memory.assert_not_called()

    def test_authorized_delete_is_limited_to_a_supplied_candidate_id(self):
        agent, memory_service, _ = _agent(
            [{"actions": [{"action": "delete", "memory_id": "cross-tenant"}], "summary": "delete"}]
        )
        result = agent.curate([], [_memory()], _scope(delete_authorized=True), timeout=1.0)
        self.assertEqual(result.status, "fallback")
        memory_service.delete_memory.assert_not_called()

    def test_business_invalid_non_destructive_output_gets_one_correction_retry(self):
        agent, memory_service, llm = _agent([
            {"actions": [{"action": "create"}], "summary": "invalid"},
            {"actions": [{"action": "create", "content": "User prefers Hebrew replies."}], "summary": "fixed"},
        ])
        result = agent.curate(
            [{"role": "user", "content": "Please remember that I prefer Hebrew replies."}],
            [],
            _scope(),
            timeout=1.0,
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(llm.call_count, 2)
        self.assertTrue(llm.call_args_list[1].args[1]["validation_feedback"])
        memory_service.write_memory.assert_called_once()

    def test_structured_output_and_provider_failures_use_distinct_budgets(self):
        agent, _, llm = _agent([
            MemoryAgentLLMError("bad json", kind="structured_output"),
            MemoryAgentLLMError("timeout", kind="provider"),
            {"actions": [], "summary": "safe"},
        ])
        result = agent.curate([], [], _scope(), timeout=1.0)
        self.assertEqual(result.status, "success")
        self.assertEqual(llm.call_count, 3)
        self.assertEqual(result.provenance["retries"], {
            "structured_output": 1, "business_validation": 0,
            "tool_validation": 0, "provider": 1,
        })

    def test_cross_tenant_candidate_is_rejected_before_model_execution(self):
        agent, memory_service, llm = _agent([{"actions": [], "summary": "unused"}])
        with self.assertRaisesRegex(MemoryAgentError, "tenant"):
            agent.curate([], [_memory(tenant_id="tenant-2")], _scope(), timeout=1.0)
        llm.assert_not_called()
        memory_service.write_memory.assert_not_called()

    def test_context_and_candidate_arrays_are_bounded_before_model_execution(self):
        agent, _, llm = _agent([{"actions": [], "summary": "safe"}])
        history = [{"role": "user", "content": "x" * 5000} for _ in range(40)]
        existing = [_memory(f"memory-{index}") for index in range(20)]
        agent.curate(history, existing, _scope(), timeout=1.0)
        payload = llm.call_args.args[1]
        self.assertEqual(len(payload["conversation_history"]), 24)
        self.assertEqual(max(len(item["content"]) for item in payload["conversation_history"]), 4000)
        self.assertEqual(len(payload["existing_memory"]), 10)

    def test_assistant_only_inference_cannot_create_memory_even_if_the_model_requests_it(self):
        agent, memory_service, _ = _agent([
            {"actions": [{"action": "create", "content": "User prefers Rust."}], "summary": "guess"},
            {"actions": [{"action": "ignore", "reason": "no user evidence"}], "summary": "fixed"},
        ])
        result = agent.curate(
            [{"role": "assistant", "content": "The user probably prefers Rust."}],
            [],
            _scope(),
            timeout=1.0,
        )
        self.assertEqual(result.status, "success")
        memory_service.write_memory.assert_not_called()

    def test_low_confidence_and_exact_duplicate_creates_are_business_invalid(self):
        responses = [
            {"actions": [{"action": "create", "content": "The project uses Python.", "confidence": 0.2}], "summary": "bad"},
            {"actions": [{"action": "ignore", "reason": "duplicate"}], "summary": "fixed"},
        ]
        agent, memory_service, _ = _agent(responses)
        result = agent.curate(
            [{"role": "user", "content": "The project uses Python."}],
            [_memory()],
            _scope(),
            timeout=1.0,
        )
        self.assertEqual(result.status, "success")
        memory_service.write_memory.assert_not_called()
