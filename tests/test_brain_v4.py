from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SCRIPTS = REPO_ROOT / "scripts" / "ai"
sys.path.insert(0, str(AI_SCRIPTS))

from brain_core import Brain  # noqa: E402
from _brain_sources import classify_source  # noqa: E402


class BrainV4Tests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory, Path, Brain]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / ".gitignore").write_text("/.agent-private/\n", encoding="utf-8")
        src = root / "backend" / "synthetic" / "app"
        src.mkdir(parents=True)
        (src / "fixture.py").write_text(
            """from fastapi import APIRouter\n\nrouter = APIRouter()\n\ndef zz_orion_guard(review_id: str) -> bool:\n    return bool(review_id)\n\ndef zz_orion_process(review_id: str) -> bool:\n    return zz_orion_guard(review_id)\n\n@router.post('/v1/zz-orion')\ndef zz_orion_apply(review_id: str):\n    return zz_orion_process(review_id)\n""",
            encoding="utf-8",
        )
        tests = root / "backend" / "synthetic" / "app" / "tests"
        tests.mkdir(parents=True)
        (tests / "test_fixture.py").write_text(
            """from backend.synthetic.app.fixture import zz_orion_guard\n\ndef test_zz_orion_guard():\n    assert zz_orion_guard('x') is True\n""",
            encoding="utf-8",
        )
        docs = root / "docs" / "ai" / "tasks"
        docs.mkdir(parents=True)
        (docs / "ZZBRAIN-99.md").write_text("# ZZBRAIN-99\nOrion nebula guard application.\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        brain = Brain(root, root / ".agent-private" / "brain" / "brain.sqlite3")
        return td, root, brain

    def test_sync_and_exact_bm25_retrieval(self):
        td, root, brain = self.make_repo()
        self.addCleanup(td.cleanup)
        result = brain.sync(full=True)
        self.assertGreaterEqual(result["total_files"], 3)
        hits = brain.query("zz_orion_guard", top=5)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["path"], "backend/synthetic/app/fixture.py")
        semantic_words = brain.query("orion nebula guard application", top=8)
        paths = {h["path"] for h in semantic_words}
        self.assertIn("docs/ai/tasks/ZZBRAIN-99.md", paths)
        self.assertIn("backend/synthetic/app/fixture.py", paths)

    def test_graph_expands_called_symbol(self):
        td, root, brain = self.make_repo()
        self.addCleanup(td.cleanup)
        brain.sync(full=True)
        hits = brain.query("zz_orion_process", top=10)
        by_symbol = {h["symbol"]: h for h in hits}
        self.assertIn("zz_orion_guard", by_symbol)
        self.assertIn("graph:called-symbol", by_symbol["zz_orion_guard"]["reasons"])

    def test_incremental_sync_indexes_only_changed_content(self):
        td, root, brain = self.make_repo()
        self.addCleanup(td.cleanup)
        brain.sync(full=True)
        path = root / "backend" / "synthetic" / "app" / "fixture.py"
        time.sleep(0.002)
        path.write_text(path.read_text(encoding="utf-8") + "\ndef zz_brand_new_guard():\n    return True\n", encoding="utf-8")
        result = brain.sync()
        self.assertEqual(result["changed_files"], 1)
        hits = brain.query("zz_brand_new_guard", top=3)
        self.assertEqual(hits[0]["symbol"], "zz_brand_new_guard")

    def test_private_handoff_is_queryable_but_can_be_excluded(self):
        td, root, brain = self.make_repo()
        self.addCleanup(td.cleanup)
        private = root / ".agent-private"
        private.mkdir(exist_ok=True)
        (private / "HANDOFF.md").write_text("# Handoff\nSpecial phoenix quasar regression in synthetic flow.\n", encoding="utf-8")
        brain.sync(full=True)
        self.assertTrue(any(h["is_private"] for h in brain.query("phoenix quasar", top=5)))
        self.assertFalse(any(h["is_private"] for h in brain.query("phoenix quasar", top=5, public_only=True)))

    def test_context_budget_and_doctor(self):
        td, root, brain = self.make_repo()
        self.addCleanup(td.cleanup)
        brain.sync(full=True)
        packet = brain.context("orion nebula", top=10, budget_chars=2500)
        self.assertLessEqual(len(packet), 2600)
        self.assertIn("backend/synthetic/app/fixture.py", packet)
        ok, details = brain.doctor()
        self.assertTrue(ok, details)

    def test_brain_manual_is_not_authoritative(self):
        self.assertEqual(classify_source("docs/ai/BRAIN_V4.md"), "source")
        self.assertEqual(classify_source("docs/ai/RUNTIME_CONTRACT.md"), "authoritative")

    def test_feature_query_prefers_code_over_generic_instruction_match(self):
        td, root, brain = self.make_repo()
        self.addCleanup(td.cleanup)
        (root / "AGENTS.md").write_text(
            "# Instructions\nPreserve tenant isolation and authorization.\n",
            encoding="utf-8",
        )
        src = root / "backend" / "synthetic" / "app" / "tenant.py"
        src.write_text(
            "def tenant_isolation_guard(tenant_id: str) -> bool:\n    return bool(tenant_id)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        brain.sync(full=True)
        hits = brain.query("tenant isolation", top=5)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["path"], "backend/synthetic/app/tenant.py")


if __name__ == "__main__":
    unittest.main()
