"""Per-action output token budgets, from settings resolution to invocation."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.core.config import Settings
from app.services.llm_service import LLMService
from app.services.text_window import SAFETY_MARGIN_TOKENS, estimate_tokens
from app.tests._service_harness import (
    ACTION_ORDER,
    VALID_INPUTS,
    VALID_RESPONSES,
    FakeLLMClient,
    FakeLogger,
    request_message,
    settings,
)


class ActionBudgetResolutionTests(unittest.TestCase):
    """Settings own the truth table; nothing else may reinterpret it."""

    def test_action_token_budgets_resolve_independently_with_safe_fallback(self):
        resolved = settings(
            vllm_max_tokens=512,
            answer_generation_max_tokens=101,
            answer_evaluation_max_tokens=202,
            content_risk_scan_max_tokens=303,
            query_rewrite_max_tokens=404,
            memory_extraction_max_tokens=505,
        )

        expected = {
            "answer_generation": 101,
            "answer_evaluation": 202,
            "content_risk_scan": 303,
            "query_rewrite": 404,
            "memory_extraction": 505,
        }
        self.assertEqual(
            {action: resolved.max_tokens_for_request_type(action) for action in expected},
            expected,
        )
        self.assertEqual(resolved.max_tokens_for_request_type("legacy_action"), 512)

    def test_action_token_budget_defaults_match_measured_candidate(self):
        resolved = settings(vllm_max_tokens=777)

        self.assertEqual(
            {
                action: resolved.max_tokens_for_request_type(action)
                for action in Settings._ACTION_MAX_TOKEN_FIELDS
            },
            {
                "answer_generation": 128,
                "answer_evaluation": 512,
                "content_risk_scan": 128,
                "query_rewrite": 128,
                "memory_extraction": 512,
            },
        )
        self.assertEqual(resolved.max_tokens_for_request_type("unknown"), 777)

    def test_action_budget_environment_overrides_are_independent(self):
        env = {
            "ANSWER_GENERATION_MAX_TOKENS": "201",
            "ANSWER_EVALUATION_MAX_TOKENS": "202",
            "CONTENT_RISK_SCAN_MAX_TOKENS": "203",
            "QUERY_REWRITE_MAX_TOKENS": "204",
            "MEMORY_EXTRACTION_MAX_TOKENS": "205",
        }
        with patch.dict(os.environ, env, clear=False):
            resolved = Settings()

        self.assertEqual(
            [resolved.max_tokens_for_request_type(action) for action in ACTION_ORDER],
            [201, 202, 203, 204, 205],
        )

    def test_summary_budget_remains_independent(self):
        resolved = settings(summary_max_tokens=2048, answer_generation_max_tokens=128)

        self.assertEqual(resolved.summary_max_tokens, 2048)
        self.assertEqual(resolved.max_tokens_for_request_type("answer_generation"), 128)

    def test_invalid_token_budgets_are_rejected(self):
        for field_name in ("vllm_max_tokens", *Settings._ACTION_MAX_TOKEN_FIELDS.values()):
            for invalid_value in (0, -1):
                with self.subTest(field_name=field_name, invalid_value=invalid_value):
                    with self.assertRaises(ValidationError):
                        settings(**{field_name: invalid_value})

    def test_token_budget_cannot_exceed_context_window(self):
        with self.assertRaises(ValidationError):
            settings(
                vllm_max_model_len=1024,
                summary_max_tokens=512,
                answer_generation_max_tokens=1025,
            )


class BudgetReachesInvocationTests(unittest.TestCase):
    """Wiring only: the resolved budget must survive into the provider call."""

    def test_request_specific_budget_reaches_typed_invocation(self):
        client = FakeLLMClient({"content_risk_scan": VALID_RESPONSES["content_risk_scan"]})
        service = LLMService(client, FakeLogger(), settings(content_risk_scan_max_tokens=89))

        reply = service.execute(
            request_message("content_risk_scan", VALID_INPUTS["content_risk_scan"])
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(client.invocations[0].max_tokens, 89)
        self.assertEqual(client.invocations[0].metadata["structured_output_hint"], "json_object")

    def test_all_candidate_budgets_reach_typed_invocations(self):
        client = FakeLLMClient(VALID_RESPONSES)
        service = LLMService(client, FakeLogger(), settings())

        for action in ACTION_ORDER:
            with self.subTest(action=action):
                reply = service.execute(request_message(action, VALID_INPUTS[action]))
                self.assertEqual(reply.status, "success")

        self.assertEqual(
            {
                invocation.metadata["request_type"]: invocation.max_tokens
                for invocation in client.invocations
            },
            {
                "answer_generation": 128,
                "answer_evaluation": 512,
                "content_risk_scan": 128,
                "query_rewrite": 128,
                "memory_extraction": 512,
            },
        )

    def test_typed_prompt_reserves_its_effective_output_budget(self):
        client = FakeLLMClient({"answer_generation": "A concise answer."})
        resolved = settings(
            vllm_max_model_len=1024,
            summary_max_tokens=512,
            answer_generation_max_tokens=128,
        )
        service = LLMService(client, FakeLogger(), resolved)

        reply = service.execute(
            request_message(
                "answer_generation",
                {"question": "What?", "retrieved_context": "context " * 5000},
            )
        )

        invocation = client.invocations[0]
        self.assertEqual(reply.status, "success")
        self.assertLessEqual(
            estimate_tokens(invocation.system_prompt)
            + estimate_tokens(invocation.raw_prompt)
            + invocation.max_tokens
            + SAFETY_MARGIN_TOKENS,
            resolved.vllm_max_model_len,
        )
