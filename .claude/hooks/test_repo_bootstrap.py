from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("repo_bootstrap", HERE / "repo-bootstrap.py")
assert SPEC and SPEC.loader
rb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rb)


class RepoBootstrapTests(unittest.TestCase):
    def make_repo(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / ".agent-private").mkdir()
        (root / ".claude" / "hooks").mkdir(parents=True)
        (root / "docs" / "ai" / "tasks").mkdir(parents=True)
        (root / "frontend" / "src" / "features" / "files").mkdir(parents=True)
        return td, root

    def test_query_strips_literal_task_id_from_prompt_and_title(self):
        spec = """# FILES-LIST-01 — Knowledge operations table
## Goal
Replace the current document-card gallery with a scalable operational document interface.
## Bulk actions
Support re-index and delete.
## Tests
Search, filter, sort, pipeline states and bulk actions.
"""
        query = rb.build_brain_query("Implement FILES-LIST-01 rerun support", "FILES-LIST-01", spec)
        self.assertNotIn("FILES-LIST-01", query.upper())
        words = set(query.split())
        self.assertIn("files", words)
        self.assertIn("list", words)
        self.assertTrue({"document", "reindex", "delete", "table", "pipeline"} & words)

    def test_diversification_suppresses_task_and_prefers_source_and_tests(self):
        results = []
        for i in range(20):
            results.append({
                "chunk_id": f"task-{i}",
                "path": "docs/ai/tasks/FILES-LIST-01.md",
                "start_line": i + 1,
                "source_class": "task",
                "excerpt": "task section",
            })
        results += [
            {"chunk_id": "t1", "path": "frontend/src/features/files/FilesTab.test.jsx", "start_line": 1, "source_class": "source", "excerpt": "bulk delete test"},
            {"chunk_id": "s1", "path": "frontend/src/features/files/FilesTab.jsx", "start_line": 1, "source_class": "source", "excerpt": "document table"},
            {"chunk_id": "s2", "path": "frontend/src/features/files/hooks/useFiles.js", "start_line": 1, "source_class": "source", "excerpt": "reindex file"},
            {"chunk_id": "s3", "path": "frontend/src/features/files/services/fileService.js", "start_line": 1, "source_class": "source", "excerpt": "rerun stage"},
        ]
        picked = rb.diversify_results(results, task_path="docs/ai/tasks/FILES-LIST-01.md", limit=10)
        paths = [str(x["path"]) for x in picked]
        self.assertNotIn("docs/ai/tasks/FILES-LIST-01.md", paths)
        self.assertEqual(paths[0], "frontend/src/features/files/FilesTab.jsx")
        self.assertGreaterEqual(sum(p.startswith("frontend/") for p in paths), 4)

    def test_closed_gate_allows_git_and_task_read_but_blocks_exploration(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        task = root / "docs" / "ai" / "tasks" / "FILES-LIST-01.md"
        task.write_text("# FILES-LIST-01\n", encoding="utf-8")
        session = "s1"

        git_call = {"tool_name": "Bash", "tool_input": {"command": "git status --short && git branch --show-current"}}
        self.assertEqual(rb._pre_mode(git_call, root, session), 0)

        task_read = {"tool_name": "Read", "tool_input": {"file_path": str(task)}}
        self.assertEqual(rb._pre_mode(task_read, root, session), 0)

        grep_call = {"tool_name": "Grep", "tool_input": {"pattern": "reindex", "path": str(root / "frontend")}}
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(rb._pre_mode(grep_call, root, session), 2)
        self.assertIn("Repo Bootstrap gate", err.getvalue())
        self.assertIn("repo-bootstrap.py", err.getvalue())

    def test_task_read_records_exact_task_for_next_hint(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        task = root / "docs" / "ai" / "tasks" / "FILES-LIST-01.md"
        task.write_text("# FILES-LIST-01\n", encoding="utf-8")
        session = "s2"
        data = {"tool_name": "Read", "tool_input": {"file_path": str(task)}}
        rb._post_mode(data, root, session)
        state = rb._load_state(root, session)
        self.assertEqual(state["task_id"], "FILES-LIST-01")
        self.assertEqual(state["status"], "pending")
        hint = rb._bootstrap_hint(root, session, state)
        self.assertIn('--task "FILES-LIST-01"', hint)
        self.assertIn(f'--session "{session}"', hint)

    def test_bootstrap_command_requires_matching_session(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        session = "s3"
        script = root / ".claude" / "hooks" / "repo-bootstrap.py"
        good = {"tool_name": "PowerShell", "tool_input": {"command": f'py -3.12 "{script}" bootstrap --session "{session}" --query "files reindex"'}}
        self.assertEqual(rb._pre_mode(good, root, session), 0)
        bad = {"tool_name": "PowerShell", "tool_input": {"command": f'py -3.12 "{script}" bootstrap --session "other" --query "files reindex"'}}
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(rb._pre_mode(bad, root, session), 2)
        self.assertIn("session id does not match", err.getvalue())

    def test_posttooluse_opens_only_after_successful_bootstrap_state(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        session = "s4"
        script = root / ".claude" / "hooks" / "repo-bootstrap.py"
        cmd = f'py -3.12 "{script}" bootstrap --session "{session}" --query "files reindex"'
        rb._write_state(root, session, {"status": "pending"})
        rb._post_mode({"tool_name": "PowerShell", "tool_input": {"command": cmd}}, root, session)
        self.assertEqual(rb._load_state(root, session)["status"], "pending")
        rb._write_state(root, session, {"status": "bootstrap_succeeded", "source_result_count": 3})
        rb._post_mode({"tool_name": "PowerShell", "tool_input": {"command": cmd}}, root, session)
        self.assertEqual(rb._load_state(root, session)["status"], "ready")

    def test_new_task_spec_relocks_ready_session(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        session = "s5"
        next_task = root / "docs" / "ai" / "tasks" / "NEXT-16-01.md"
        next_task.write_text("# NEXT-16-01\n", encoding="utf-8")
        rb._write_state(root, session, {"status": "ready", "task_id": "FILES-LIST-01"})
        data = {"tool_name": "Read", "tool_input": {"file_path": str(next_task)}}
        self.assertEqual(rb._pre_mode(data, root, session), 0)
        state = rb._load_state(root, session)
        self.assertEqual(state["status"], "pending")
        self.assertEqual(state["task_id"], "NEXT-16-01")

    def test_large_native_read_is_blocked_after_ready(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        session = "s6"
        source = root / "frontend" / "src" / "features" / "files" / "Huge.jsx"
        source.write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
        rb._write_state(root, session, {"status": "ready"})
        full = {"tool_name": "Read", "tool_input": {"file_path": str(source)}}
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(rb._pre_mode(full, root, session), 2)
        self.assertIn("over 250 lines", err.getvalue())
        bounded = {"tool_name": "Read", "tool_input": {"file_path": str(source), "offset": 1, "limit": 120}}
        self.assertEqual(rb._pre_mode(bounded, root, session), 0)

    def test_large_cat_is_blocked_but_bounded_sed_is_allowed(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        session = "s7"
        source = root / "frontend" / "src" / "features" / "files" / "Huge.jsx"
        source.write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
        rb._write_state(root, session, {"status": "ready"})
        cat = {"cwd": str(root / "frontend"), "tool_name": "Bash", "tool_input": {"command": "cat src/features/files/Huge.jsx"}}
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(rb._pre_mode(cat, root, session), 2)
        self.assertIn("would print all", err.getvalue())
        sed = {"cwd": str(root / "frontend"), "tool_name": "Bash", "tool_input": {"command": "sed -n '1,120p' src/features/files/Huge.jsx"}}
        self.assertEqual(rb._pre_mode(sed, root, session), 0)

    def test_bootstrap_fails_closed_when_brain_refresh_or_query_fails(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        task = root / "docs" / "ai" / "tasks" / "FILES-LIST-01.md"
        task.write_text("# FILES-LIST-01\n## Goal\nBuild document table.\n", encoding="utf-8")
        original = rb._brain_query
        rb._brain_query = lambda _root, _query: (_ for _ in ()).throw(RuntimeError("stale sync failed"))
        try:
            err = io.StringIO()
            with redirect_stderr(err):
                rc = rb._bootstrap(root, "s-fail", "FILES-LIST-01", "")
            self.assertEqual(rc, 2)
            self.assertIn("stale sync failed", err.getvalue())
            state = rb._load_state(root, "s-fail")
            self.assertNotEqual(state.get("status"), "bootstrap_succeeded")
            self.assertNotEqual(state.get("status"), "ready")
        finally:
            rb._brain_query = original

    def test_bootstrap_writes_source_state_and_packet_to_stdout(self):
        td, root = self.make_repo()
        self.addCleanup(td.cleanup)
        task = root / "docs" / "ai" / "tasks" / "FILES-LIST-01.md"
        task.write_text("# FILES-LIST-01 — Knowledge operations table\n## Goal\nBuild document table reindex delete.\n", encoding="utf-8")
        results = [
            {"chunk_id": "s1", "path": "frontend/src/features/files/FilesTab.jsx", "start_line": 10, "end_line": 90, "symbol": "FilesTab", "source_class": "source", "reasons": ["bm25"], "excerpt": "document table reindex"},
            {"chunk_id": "s2", "path": "frontend/src/features/files/FilesTab.test.jsx", "start_line": 1, "end_line": 80, "symbol": "<module>", "source_class": "source", "reasons": ["bm25"], "excerpt": "bulk delete tests"},
        ]
        original = rb._brain_query
        rb._brain_query = lambda _root, _query: (results, False)
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                rc = rb._bootstrap(root, "s8", "FILES-LIST-01", "")
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("frontend/src/features/files/FilesTab.jsx", text)
            state = rb._load_state(root, "s8")
            self.assertEqual(state["status"], "bootstrap_succeeded")
            self.assertGreaterEqual(state["source_result_count"], 2)
            self.assertNotIn("FILES-LIST-01", state["brain_query"].upper())
        finally:
            rb._brain_query = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
