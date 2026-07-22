"""Tests for context-window budgeting and text splitting."""
from __future__ import annotations

import unittest

from app.core.config import Settings
from app.services.text_window import (
    ContextWindowResolver,
    estimate_tokens,
    split_text,
)


class FakeLogger:
    """Simple in-memory logger for service tests."""

    def __init__(self):
        self.entries = []

    def log(self, location, message, data=None, hypothesis_id="A"):
        self.entries.append({"location": location, "message": message, "data": data or {}})


class FakeClient:
    """Client stub exposing only the context-window probe."""

    def __init__(self, window=None, error=None):
        self.window = window
        self.error = error
        self.calls = 0

    def get_context_window(self, model):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.window


def marked_text(marker_count, filler=200):
    """Build text with distinctive, evenly spread markers."""
    return "\n\n".join(f"<<M{index}>> {'word ' * filler}" for index in range(marker_count))


class SplitTextTests(unittest.TestCase):
    """Splitting must lose nothing and use as few chunks as possible."""

    def test_short_text_is_a_single_chunk(self):
        self.assertEqual(split_text("hello world", max_chars=100), ["hello world"])

    def test_every_marker_survives_the_split(self):
        text = marked_text(40)
        chunks = split_text(text, max_chars=2000, overlap_chars=200)

        self.assertGreater(len(chunks), 1)
        for index in range(40):
            marker = f"<<M{index}>>"
            self.assertTrue(
                any(marker in chunk for chunk in chunks),
                msg=f"{marker} was dropped by the splitter",
            )

    def test_no_chunk_exceeds_the_budget(self):
        chunks = split_text(marked_text(40), max_chars=2000, overlap_chars=200)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 2000)

    def test_uses_as_few_chunks_as_possible(self):
        text = marked_text(40)
        chunks = split_text(text, max_chars=2000, overlap_chars=100)
        # Every chunk but the last should be filled to most of the budget,
        # otherwise the splitter is producing more LLM calls than necessary.
        for chunk in chunks[:-1]:
            self.assertGreater(len(chunk), 2000 * 0.5)

    def test_consecutive_chunks_overlap(self):
        chunks = split_text(marked_text(40), max_chars=2000, overlap_chars=300)
        tail = chunks[0][-200:]
        self.assertIn(tail, chunks[1])

    def test_text_without_separators_still_terminates(self):
        chunks = split_text("x" * 5000, max_chars=1000, overlap_chars=100)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 1000)

    def test_overlap_wider_than_budget_does_not_stall(self):
        chunks = split_text(marked_text(20), max_chars=500, overlap_chars=5000)
        self.assertLess(len(chunks), 200)


class EstimateTokensTests(unittest.TestCase):
    """Token estimation must be conservative (never under-count badly)."""

    def test_estimate_scales_with_length(self):
        self.assertGreater(estimate_tokens("a" * 4000), estimate_tokens("a" * 1000))

    def test_empty_text_is_zero(self):
        self.assertEqual(estimate_tokens(""), 0)


class ContextWindowResolverTests(unittest.TestCase):
    """Discovery first, configured fallback second."""

    def setUp(self):
        self.config = Settings(vllm_max_model_len=6144, vllm_max_tokens=512)
        self.logger = FakeLogger()

    def test_uses_discovered_window(self):
        resolver = ContextWindowResolver(FakeClient(window=8192), self.config, self.logger)
        self.assertEqual(resolver.context_tokens("m"), 8192)

    def test_falls_back_to_config_when_discovery_returns_nothing(self):
        resolver = ContextWindowResolver(FakeClient(window=None), self.config, self.logger)
        self.assertEqual(resolver.context_tokens("m"), 6144)

    def test_falls_back_to_config_when_discovery_raises(self):
        resolver = ContextWindowResolver(
            FakeClient(error=RuntimeError("vllm down")), self.config, self.logger
        )
        self.assertEqual(resolver.context_tokens("m"), 6144)

    def test_falls_back_when_client_has_no_probe(self):
        resolver = ContextWindowResolver(object(), self.config, self.logger)
        self.assertEqual(resolver.context_tokens("m"), 6144)

    def test_discovery_result_is_cached_per_model(self):
        client = FakeClient(window=8192)
        resolver = ContextWindowResolver(client, self.config, self.logger)
        resolver.context_tokens("m")
        resolver.context_tokens("m")
        self.assertEqual(client.calls, 1)

    def test_budget_leaves_room_for_output_and_prompt(self):
        resolver = ContextWindowResolver(FakeClient(window=6144), self.config, self.logger)
        budget = resolver.input_budget_chars("m", reserved_tokens=100)

        # Whatever fits in the budget plus the output and the prompt overhead
        # must still land inside the window.
        self.assertLess(estimate_tokens("x" * budget) + 512 + 100, 6144)
        self.assertGreater(budget, 0)

    def test_budget_is_positive_even_on_a_tiny_window(self):
        resolver = ContextWindowResolver(FakeClient(window=600), self.config, self.logger)
        self.assertGreater(resolver.input_budget_chars("m", reserved_tokens=50), 0)


if __name__ == "__main__":
    unittest.main()
