from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ai" / "repo_bootstrap.py"
SPEC = importlib.util.spec_from_file_location("repo_bootstrap", SCRIPT)
assert SPEC and SPEC.loader
repo_bootstrap = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = repo_bootstrap
SPEC.loader.exec_module(repo_bootstrap)


class RepoBootstrapTests(unittest.TestCase):
    SPEC_TEXT = """# LLM-CTRL-01
## Goal
Make llm_agent the canonical typed LLM execution boundary.
## Primary scope
- `backend/llm_agent/app/services/llm_service.py`
- provider adapters
- prompt registry/config
- Memory LLM callers
- requirements/Dockerfile
- tests
## Required behavior
- Route Memory title/summary/curation model calls through typed llm_agent requests.
- Split execution into plan/render/invoke/decode/validate/telemetry responsibilities.
"""

    def test_query_plan_strips_task_id_and_splits_scope(self):
        plan = repo_bootstrap.build_query_plan(
            "LLM-CTRL-01 unify LLM control plane typed providers",
            "LLM-CTRL-01",
            self.SPEC_TEXT,
        )
        queries = [item.query for item in plan]
        self.assertTrue(any("llm_service" in query for query in queries))
        self.assertTrue(any("provider" in query and "adapter" in query for query in queries))
        self.assertTrue(any("prompt" in query and "registry" in query for query in queries))
        self.assertTrue(any("memory" in query and "caller" in query for query in queries))
        self.assertFalse(any("LLM-CTRL-01" in query for query in queries))

    def test_explicit_scope_owner_is_forced_first(self):
        rows = [
            {
                "chunk_id": "generic",
                "path": "backend/llm_agent/app/core/errors.py",
                "symbol": "StreamingNotSupportedException",
                "excerpt": "LLM provider cannot stream tokens",
                "source_class": "source",
                "bootstrap_retrieval_score": 5.0,
            },
            {
                "chunk_id": "owner",
                "path": "backend/llm_agent/app/services/llm_service.py",
                "symbol": "LLMService.execute",
                "excerpt": "typed execution request prompt registry provider",
                "source_class": "source",
                "bootstrap_retrieval_score": 0.01,
            },
        ]
        out = repo_bootstrap.diversify_results(
            rows,
            limit=2,
            explicit_paths=["backend/llm_agent/app/services/llm_service.py"],
            scope_bullets=repo_bootstrap._scope_bullets(self.SPEC_TEXT),
            query_terms=["typed", "provider"],
        )
        self.assertEqual(out[0]["path"], "backend/llm_agent/app/services/llm_service.py")

    def test_memory_llm_scope_rejects_generic_controller(self):
        rows = [
            {
                "chunk_id": "controller",
                "path": "backend/memory/app/rest/controllers.py",
                "symbol": "MemoryController",
                "excerpt": "memory rest controller health chat list",
                "source_class": "source",
                "bootstrap_retrieval_score": 2.0,
            },
            {
                "chunk_id": "caller",
                "path": "backend/memory/app/services/chat_exit_service.py",
                "symbol": "ChatExitService._request_typed_llm",
                "excerpt": "typed llm rpc request for chat title summary and memory curation",
                "source_class": "source",
                "bootstrap_retrieval_score": 0.1,
            },
        ]
        bullet = "Memory LLM callers"
        self.assertEqual(repo_bootstrap._scope_match_score(rows[0], bullet), 0.0)
        self.assertGreater(repo_bootstrap._scope_match_score(rows[1], bullet), 10.0)
        out = repo_bootstrap.diversify_results(
            rows,
            limit=2,
            scope_bullets=[bullet],
            query_terms=["memory", "llm", "title", "summary", "curation"],
        )
        self.assertEqual(out[0]["path"], "backend/memory/app/services/chat_exit_service.py")

    def test_prompt_registry_scope_beats_generic_prompt_helper(self):
        rows = [
            {
                "chunk_id": "base",
                "path": "backend/llm_agent/app/llm/prompts/_base.py",
                "symbol": "PromptRegistryEntry",
                "excerpt": "prompt builder parser defaults",
                "source_class": "source",
                "bootstrap_retrieval_score": 2.0,
            },
            {
                "chunk_id": "registry",
                "path": "backend/llm_agent/app/llm/prompt_registry.py",
                "symbol": "PromptRegistry",
                "excerpt": "resolve prompt builders parsers defaults typed execution",
                "source_class": "source",
                "bootstrap_retrieval_score": 0.1,
            },
        ]
        out = repo_bootstrap.diversify_results(
            rows,
            limit=2,
            scope_bullets=["prompt registry/config"],
            query_terms=["prompt", "registry", "config"],
        )
        self.assertEqual(out[0]["path"], "backend/llm_agent/app/llm/prompt_registry.py")

    def test_diversification_caps_path_and_suppresses_task(self):
        rows = [
            {"chunk_id": "t1", "path": "docs/ai/tasks/LLM-CTRL-01.md", "symbol": "Goal", "source_class": "task"},
            {"chunk_id": "s1", "path": "backend/llm_agent/app/services/llm_service.py", "symbol": "A", "source_class": "source"},
            {"chunk_id": "s2", "path": "backend/llm_agent/app/services/llm_service.py", "symbol": "B", "source_class": "source"},
            {"chunk_id": "s3", "path": "backend/llm_agent/app/services/llm_service.py", "symbol": "C", "source_class": "source"},
            {"chunk_id": "x1", "path": "backend/llm_agent/app/tests/core/test_llm_schemas.py", "symbol": "T", "source_class": "source"},
        ]
        out = repo_bootstrap.diversify_results(
            rows,
            task_path="docs/ai/tasks/LLM-CTRL-01.md",
            limit=12,
            explicit_paths=["backend/llm_agent/app/services/llm_service.py"],
            scope_bullets=["tests"],
            query_terms=["typed"],
        )
        paths = [row["path"] for row in out]
        self.assertNotIn("docs/ai/tasks/LLM-CTRL-01.md", paths)
        self.assertLessEqual(paths.count("backend/llm_agent/app/services/llm_service.py"), 2)
        self.assertIn("backend/llm_agent/app/tests/core/test_llm_schemas.py", paths)

    def test_combined_llm_ctrl_packet_covers_real_owners(self):
        rows = [
            {"chunk_id": "noise1", "path": "backend/llm_agent/app/cache/memory.py", "symbol": "MemoryModelCache", "excerpt": "model memory cache", "source_class": "source", "bootstrap_retrieval_score": 4.0},
            {"chunk_id": "noise2", "path": "backend/llm_agent/app/core/errors.py", "symbol": "StreamingNotSupportedException", "excerpt": "provider error", "source_class": "source", "bootstrap_retrieval_score": 3.0},
            {"chunk_id": "owner", "path": "backend/llm_agent/app/services/llm_service.py", "symbol": "LLMService.execute", "excerpt": "typed execution provider finish reason", "source_class": "source", "bootstrap_retrieval_score": 0.2},
            {"chunk_id": "registry", "path": "backend/llm_agent/app/llm/prompt_registry.py", "symbol": "PromptRegistry", "excerpt": "typed prompt registry config", "source_class": "source", "bootstrap_retrieval_score": 0.2},
            {"chunk_id": "memory", "path": "backend/memory/app/services/chat_exit_service.py", "symbol": "ChatExitService._request_typed_llm", "excerpt": "typed rpc chat title summary memory curation", "source_class": "source", "bootstrap_retrieval_score": 0.15},
            {"chunk_id": "provider", "path": "backend/llm_agent/app/llm/implementations/vllm.py", "symbol": "VLLMClient", "excerpt": "provider adapter vllm", "source_class": "source", "bootstrap_retrieval_score": 0.15},
            {"chunk_id": "tests", "path": "backend/llm_agent/app/tests/core/test_llm_schemas.py", "symbol": "test_typed_request", "excerpt": "typed request schema", "source_class": "source", "bootstrap_retrieval_score": 0.1},
        ]
        explicit = ["backend/llm_agent/app/services/llm_service.py"]
        bullets = repo_bootstrap._scope_bullets(self.SPEC_TEXT)
        out = repo_bootstrap.diversify_results(
            rows,
            limit=7,
            explicit_paths=explicit,
            scope_bullets=bullets,
            query_terms=["llm", "typed", "provider", "prompt", "registry", "memory", "summary", "curation"],
        )
        paths = [item["path"] for item in out]
        self.assertEqual(paths[0], "backend/llm_agent/app/services/llm_service.py")
        self.assertIn("backend/llm_agent/app/llm/prompt_registry.py", paths[:4])
        self.assertIn("backend/memory/app/services/chat_exit_service.py", paths[:5])
        self.assertIn("backend/llm_agent/app/tests/core/test_llm_schemas.py", paths)
        self.assertLess(paths.index("backend/llm_agent/app/llm/prompt_registry.py"), paths.index("backend/llm_agent/app/core/errors.py"))


    def test_text_output_is_ascii_safe_for_windows_terminal(self):
        payload = {
            "task_id": "LLM-CTRL-01",
            "task_path": "docs/ai/tasks/LLM-CTRL-01.md",
            "synced": False,
            "query_plan": [{"label": "scope:1", "query": "llm service", "weight": 1.0}],
            "results": [{
                "path": "backend/llm_agent/app/services/llm_service.py",
                "start_line": 1,
                "end_line": 10,
                "symbol": "LLMService",
                "source_class": "source",
                "reasons": ["exact"],
                "excerpt": "typed execution",
            }],
        }
        text = repo_bootstrap.render_packet(payload)
        text.encode("ascii")
        self.assertIn(" -- `LLMService`", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
