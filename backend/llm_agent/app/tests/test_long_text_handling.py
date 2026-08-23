"""Tests for map-reduce summarization and budgeted keyword extraction."""
from __future__ import annotations

import unittest

from app.core.config import Settings
from app.llm.interfaces import ILLMClient, LLMGenerationResult, LLMInvocation, LLMUsage
from app.services.metadata_service import MetadataService
from app.services.summary_service import SummaryService
from app.services.text_window import estimate_tokens


class FakeLogger:
    """Simple in-memory logger for service tests."""

    def __init__(self):
        self.entries = []

    def log(self, location, message, data=None, hypothesis_id="A"):
        self.entries.append({"location": location, "message": message, "data": data or {}})


class RecordingClient(ILLMClient):
    """Record every prompt sent so context growth can be asserted on."""

    def __init__(self, window=6144, reply="This is a generated summary of the section.", unique_replies=False):
        self.window = window
        self.reply = reply
        self.unique_replies = unique_replies
        self.prompts = []
        self.outputs = []
        self.invocations = []

    def generate(self, invocation: LLMInvocation) -> LLMGenerationResult:
        self.prompts.append(invocation.to_prompt())
        self.invocations.append(invocation)
        output = f"{self.reply} [{len(self.outputs)}]" if self.unique_replies else self.reply
        self.outputs.append(output)
        return LLMGenerationResult(raw_output=output, usage=LLMUsage(provider="fake"))

    def list_models(self):
        return ["fake-model"]

    def is_available(self) -> bool:
        return True

    def get_context_window(self, model):
        return self.window


def build_config(**overrides):
    defaults = {
        "llm_implementation": "vllm",
        "summary_model": "fake-model",
        "metadata_model": "fake-model",
        "vllm_max_model_len": 6144,
        "vllm_max_tokens": 512,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class SummaryChunkingTests(unittest.TestCase):
    """Long documents are summarized in pieces, then joined into one summary."""

    def setUp(self):
        self.config = build_config()
        self.logger = FakeLogger()

    def test_short_text_uses_a_single_call(self):
        client = RecordingClient()
        service = SummaryService(client, self.logger, self.config)

        service.generate_summary("A short document about widgets.")

        self.assertEqual(len(client.prompts), 1)

    def test_long_text_sections_are_concatenated(self):
        client = RecordingClient(unique_replies=True)
        service = SummaryService(client, self.logger, self.config)

        summary = service.generate_summary("word " * 40000)

        # Every call summarizes one section; there is no separate combine pass.
        self.assertGreater(len(client.prompts), 1)
        # The final summary is each section summary joined as continuous prose.
        self.assertEqual(summary, "\n\n".join(client.outputs))

    def test_no_prompt_exceeds_the_context_window(self):
        client = RecordingClient(window=6144)
        service = SummaryService(client, self.logger, self.config)

        service.generate_summary("word " * 40000)

        for prompt in client.prompts:
            # Prompt tokens plus the reserved (larger) summary output must fit.
            self.assertLess(estimate_tokens(prompt) + self.config.summary_max_tokens, 6144)

    def test_summary_calls_request_the_larger_token_budget(self):
        client = RecordingClient()
        service = SummaryService(client, self.logger, self.config)

        service.generate_summary("A short document about widgets.")

        # Summaries must not inherit the small chat default, or they truncate
        # mid-sentence; every call asks for the summary budget.
        self.assertTrue(client.invocations)
        for invocation in client.invocations:
            self.assertEqual(invocation.max_tokens, self.config.summary_max_tokens)

    def test_single_document_is_framed_as_a_summarization_task(self):
        client = RecordingClient()
        service = SummaryService(client, self.logger, self.config)

        # The legacy "TL;DR" prompt made the model continue the document as
        # chat; it must be replaced with an explicit summarize instruction.
        service.generate_summary("A short document about widgets.", prompt_prefix="TL;DR")

        prompt = client.prompts[0]
        self.assertIn("Summarize the following document", prompt)
        self.assertNotEqual(prompt.split("\n\n")[0].strip(), "TL;DR")

    def test_all_source_text_reaches_the_model(self):
        client = RecordingClient()
        service = SummaryService(client, self.logger, self.config)
        text = "\n\n".join(f"<<M{index}>> {'word ' * 200}" for index in range(60))

        service.generate_summary(text)

        sent = "\n".join(client.prompts)
        for index in range(60):
            self.assertIn(f"<<M{index}>>", sent, msg=f"marker {index} never reached the model")

    def test_a_smaller_window_produces_more_calls(self):
        text = "word " * 40000
        wide = RecordingClient(window=8192)
        narrow = RecordingClient(window=2048)

        SummaryService(wide, self.logger, self.config).generate_summary(text)
        SummaryService(narrow, self.logger, self.config).generate_summary(text)

        self.assertGreater(len(narrow.prompts), len(wide.prompts))


class MetadataBudgetTests(unittest.TestCase):
    """Keyword extraction must respect the same window."""

    def setUp(self):
        self.config = build_config()
        self.logger = FakeLogger()

    def test_long_text_prompt_stays_inside_the_window(self):
        client = RecordingClient(reply='{"keywords": ["a","b","c","d","e","f","g","h","i","j"]}')
        service = MetadataService(client, self.logger, self.config)

        service.extract_keywords("word " * 40000)

        self.assertTrue(client.prompts)
        for prompt in client.prompts:
            self.assertLess(estimate_tokens(prompt) + 512, 6144)

    def test_returns_ten_keywords(self):
        client = RecordingClient(reply='{"keywords": ["a","b","c","d","e","f","g","h","i","j"]}')
        service = MetadataService(client, self.logger, self.config)

        keywords = service.extract_keywords("word " * 40000)

        self.assertEqual(len(keywords), 10)


if __name__ == "__main__":
    unittest.main()
