"""Contract tests for repo-brain enumeration, authority and cache hygiene.

The brain is only useful if it indexes current repository source and nothing
else: task-local tool caches must never enter enumeration, generated output must
never act as a content source, and current authoritative runtime docs must
outrank runtime text frozen inside old task specs or history.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts" / "ai"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_brain_test_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


brain_sources = _load("_brain_sources")
brain_query = _load("brain_query")
validate_ai_memory = _load("validate_ai_memory")


EXCLUDED_DIRS = [
    ".agent-private",
    ".uv-cache",
    ".uv-cache-safe01",
    ".uv-cache-safe01-memory",
    ".uv-python-safe01",
    ".uv-python-safe01-memory",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
]


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def sample_repo(tmp_path):
    """A throwaway Git repository holding source, caches and generated output."""
    _git("init", "-q", cwd=tmp_path)
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "backend" / "untracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git("add", "backend/tracked.py", cwd=tmp_path)

    for name in EXCLUDED_DIRS:
        directory = tmp_path / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "cached.py").write_text("CACHE = True\n", encoding="utf-8")

    generated = tmp_path / "docs" / "ai" / "generated"
    generated.mkdir(parents=True)
    (generated / "FILE_INDEX.json").write_text("{}\n", encoding="utf-8")

    tasks = tmp_path / "docs" / "ai" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "OLD-01.md").write_text("# OLD-01\n", encoding="utf-8")
    # Agent docs are Git-ignored in the real repository; the brain must still see them.
    (tmp_path / ".gitignore").write_text("/docs/ai\n", encoding="utf-8")
    return tmp_path


# ── File enumeration ────────────────────────────────────────


@pytest.mark.parametrize("use_git", [True, False])
def test_enumeration_includes_tracked_and_untracked_source(sample_repo, use_git):
    found = brain_sources.enumerate_sources(sample_repo, use_git=use_git)
    assert "backend/tracked.py" in found
    assert "backend/untracked.py" in found


@pytest.mark.parametrize("use_git", [True, False])
def test_enumeration_excludes_caches_and_generated_output(sample_repo, use_git):
    found = brain_sources.enumerate_sources(sample_repo, use_git=use_git)
    for name in EXCLUDED_DIRS:
        assert f"{name}/cached.py" not in found, name
    assert "docs/ai/generated/FILE_INDEX.json" not in found


def test_enumeration_force_includes_git_ignored_agent_docs(sample_repo):
    found = brain_sources.enumerate_sources(sample_repo)
    assert "docs/ai/tasks/OLD-01.md" in found


def test_enumeration_excludes_deleted_files(sample_repo):
    (sample_repo / "backend" / "tracked.py").unlink()
    found = brain_sources.enumerate_sources(sample_repo)
    assert "backend/tracked.py" not in found
    assert "backend/untracked.py" in found


def test_forbidden_indexed_paths_reports_cache_and_private_trees():
    reported = brain_sources.forbidden_indexed_paths([
        "backend/rag/app/main.py",
        ".uv-cache-safe01/pkg/mod.py",
        ".uv-python-safe01-memory/lib/mod.py",
        ".agent-private/notes.md",
        "docs/ai/generated/FILE_INDEX.json",
    ])
    assert reported == [
        ".agent-private/notes.md",
        ".uv-cache-safe01/pkg/mod.py",
        ".uv-python-safe01-memory/lib/mod.py",
        "docs/ai/generated/FILE_INDEX.json",
    ]


# ── Gitignore behavior ──────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        ".uv-cache/pkg",
        ".uv-cache-safe01/pkg",
        ".uv-cache-safe01-memory/pkg",
        ".uv-python-safe01/bin",
        ".uv-python-safe01-memory/bin",
        ".ruff_cache/x",
        ".pytest_cache/x",
        ".mypy_cache/x",
        ".venv/x",
        ".agent-private/x",
    ],
)
def test_repository_gitignore_covers_task_local_cache_variants(path):
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO_ROOT)
    assert result.returncode == 0, f"{path} is not Git-ignored"


# ── Source authority ────────────────────────────────────────


def test_classify_source_assigns_bounded_classes():
    assert brain_sources.classify_source("AGENTS.md") == "authoritative"
    assert brain_sources.classify_source("docs/ai/RUNTIME_CONTRACT.md") == "authoritative"
    assert brain_sources.classify_source(".python-version") == "authoritative"
    assert brain_sources.classify_source("docs/ai/tasks/OLD-01.md") == "task"
    assert brain_sources.classify_source("docs/ai/memory/HISTORY.md") == "history"
    assert brain_sources.classify_source(".agent-private/CHANGE_HISTORY.jsonl") == "history"
    assert brain_sources.classify_source("docs/ai/memory/handoffs/2026-01.md") == "history"
    assert brain_sources.classify_source("backend/rag/app/main.py") == "source"


@pytest.fixture
def authority_repo(tmp_path):
    """Fixture repo where authoritative 3.12 and historical 3.11 both match."""
    (tmp_path / ".python-version").write_text("3.12\n", encoding="utf-8")
    docs = tmp_path / "docs" / "ai"
    (docs / "tasks").mkdir(parents=True)
    (docs / "memory").mkdir(parents=True)
    (docs / "RUNTIME_CONTRACT.md").write_text(
        "# Runtime Contract\n\nCanonical Python: 3.12 — the canonical Python validation runtime.\n",
        encoding="utf-8",
    )
    (docs / "tasks" / "OLD-01.md").write_text(
        "# OLD-01 — legacy task\n\nThe canonical Python validation runtime is 3.11 for this task.\n"
        "Use isolated Python 3.11 as the canonical validation runtime.\n",
        encoding="utf-8",
    )
    (docs / "memory" / "HISTORY.md").write_text(
        "- canonical Python validation runtime was 3.11 during that run.\n",
        encoding="utf-8",
    )
    # One dense private history record: many raw token hits on a single line.
    private = tmp_path / ".agent-private"
    private.mkdir()
    (private / "CHANGE_HISTORY.jsonl").write_text(
        json.dumps({
            "task": "OLD-01",
            "summary": "canonical Python validation runtime 3.11 canonical validation runtime",
            "tests": ["canonical Python 3.11 validation runtime PASS"],
        }) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_generic_runtime_query_prefers_authoritative_source(authority_repo):
    results = brain_query.run_query(authority_repo, "canonical Python validation runtime", top=10)
    assert results, "expected matches"
    top_score, top_where, top_excerpt = results[0]
    assert top_where.startswith("docs/ai/RUNTIME_CONTRACT.md"), top_where
    assert "3.12" in top_excerpt

    def best(prefix):
        return max((s for s, where, _ in results if where.startswith(prefix)), default=None)

    assert best("docs/ai/tasks/OLD-01.md") is not None, "task text must stay reachable"
    assert best(".agent-private/CHANGE_HISTORY.jsonl") is not None, "history must stay reachable"
    assert top_score > best("docs/ai/tasks/OLD-01.md")
    assert top_score > best("docs/ai/memory/HISTORY.md")
    assert top_score > best(".agent-private/CHANGE_HISTORY.jsonl")


def test_direct_task_query_still_retrieves_the_task_spec(authority_repo):
    results = brain_query.run_query(authority_repo, "OLD-01 canonical validation runtime", top=10)
    assert results[0][1].startswith("docs/ai/tasks/OLD-01.md"), results[0][1]


# ── Brain self-check ────────────────────────────────────────


def test_check_brain_index_flags_forbidden_indexed_paths(tmp_path):
    (tmp_path / "FILE_INDEX.json").write_text(
        json.dumps({"files": [
            {"path": "backend/rag/app/main.py"},
            {"path": ".uv-cache-safe01/pkg/mod.py"},
        ]}),
        encoding="utf-8",
    )
    errors: list[str] = []
    validate_ai_memory.check_brain_index(tmp_path, errors)
    assert errors == ["forbidden indexed path: .uv-cache-safe01/pkg/mod.py"]


def test_check_brain_index_accepts_clean_index(tmp_path):
    (tmp_path / "FILE_INDEX.json").write_text(
        json.dumps({"files": [{"path": "backend/rag/app/main.py"}]}), encoding="utf-8"
    )
    errors: list[str] = []
    validate_ai_memory.check_brain_index(tmp_path, errors)
    assert errors == []


def test_runtime_contract_agrees_with_python_version():
    errors: list[str] = []
    validate_ai_memory.check_runtime_contract(
        REPO_ROOT / "docs" / "ai" / "RUNTIME_CONTRACT.md",
        REPO_ROOT / ".python-version",
        errors,
    )
    assert errors == []


def test_runtime_contract_mismatch_is_reported(tmp_path):
    (tmp_path / "RUNTIME_CONTRACT.md").write_text("Canonical Python: 3.11\n", encoding="utf-8")
    (tmp_path / ".python-version").write_text("3.12\n", encoding="utf-8")
    errors: list[str] = []
    validate_ai_memory.check_runtime_contract(
        tmp_path / "RUNTIME_CONTRACT.md", tmp_path / ".python-version", errors
    )
    assert len(errors) == 1 and "3.12" in errors[0]
