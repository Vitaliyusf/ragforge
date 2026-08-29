from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ai" / "repo_bootstrap.py"
SPEC = importlib.util.spec_from_file_location("repo_bootstrap", SCRIPT)
assert SPEC and SPEC.loader
repo_bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repo_bootstrap)


class RepoBootstrapTests(unittest.TestCase):
    def test_query_strips_literal_task_id_and_keeps_scope_owner(self):
        spec = """# LLM-CTRL-01\n## Goal\nUnify typed LLM provider ownership.\n## Primary scope\n- `backend/llm_agent/app/services/llm_service.py`\n- provider adapters\n- prompt registry/config\n- Memory LLM callers\n## Required behavior\n- Route Memory title/summary/curation through typed llm_agent requests.\n"""
        ownership, behavior, anchors = repo_bootstrap.build_brain_queries(
            "LLM-CTRL-01 unify LLM control plane typed providers",
            "LLM-CTRL-01",
            spec,
        )
        self.assertNotIn("LLM-CTRL-01", ownership)
        self.assertNotIn("LLM-CTRL-01", behavior)
        self.assertIn("llm_service", ownership)
        self.assertIn("llm_service", anchors)
        self.assertIn("curation", behavior)

    def test_scope_rerank_beats_generic_core_matches(self):
        rows = [
            {
                "chunk_id": "generic",
                "path": "backend/llm_agent/app/core/errors.py",
                "symbol": "StreamingNotSupportedException",
                "excerpt": "LLM provider cannot stream tokens",
                "source_class": "source",
                "bootstrap_retrieval_score": 1.0,
            },
            {
                "chunk_id": "owner",
                "path": "backend/llm_agent/app/services/llm_service.py",
                "symbol": "LLMService.execute",
                "excerpt": "typed execution request prompt registry provider",
                "source_class": "source",
                "bootstrap_retrieval_score": 0.2,
            },
            {
                "chunk_id": "registry",
                "path": "backend/llm_agent/app/llm/prompt_registry.py",
                "symbol": "PromptRegistry",
                "excerpt": "prompt registry",
                "source_class": "source",
                "bootstrap_retrieval_score": 0.1,
            },
            {
                "chunk_id": "test",
                "path": "backend/llm_agent/app/tests/core/test_llm_schemas.py",
                "symbol": "test_typed_request",
                "excerpt": "typed request",
                "source_class": "source",
                "bootstrap_retrieval_score": 0.1,
            },
        ]
        out = repo_bootstrap.diversify_results(
            rows,
            limit=4,
            anchors=["backend/llm_agent/app/services/llm_service.py", "llm_service.py", "llm_service", "provider", "prompt", "registry", "memory"],
            query_terms=["typed", "provider", "prompt", "registry"],
        )
        paths = [item["path"] for item in out]
        self.assertLess(paths.index("backend/llm_agent/app/services/llm_service.py"), paths.index("backend/llm_agent/app/core/errors.py"))
        self.assertLess(paths.index("backend/llm_agent/app/llm/prompt_registry.py"), paths.index("backend/llm_agent/app/core/errors.py"))
        self.assertTrue(set(paths[:2]) == {
            "backend/llm_agent/app/services/llm_service.py",
            "backend/llm_agent/app/llm/prompt_registry.py",
        })

    def test_diversification_suppresses_task_and_caps_one_path(self):
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
            anchors=["llm_service"],
            query_terms=["typed"],
        )
        paths = [row["path"] for row in out]
        self.assertNotIn("docs/ai/tasks/LLM-CTRL-01.md", paths)
        self.assertLessEqual(paths.count("backend/llm_agent/app/services/llm_service.py"), 2)
        self.assertIn("backend/llm_agent/app/tests/core/test_llm_schemas.py", paths)


if __name__ == "__main__":
    unittest.main(verbosity=2)
