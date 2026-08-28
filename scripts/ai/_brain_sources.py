#!/usr/bin/env python3
"""Shared source-enumeration and source-authority rules for all repo-brain tooling."""
from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Iterable

MAX_FILE_BYTES = 2 * 1024 * 1024

TEXT_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml", ".toml", ".md"}
TEXT_NAMES = {".python-version"}

EXCLUDED_DIR_PATTERNS = (
    ".git",
    ".agent-private",
    ".uv-cache",
    ".uv-cache-*",
    ".uv-python",
    ".uv-python-*",
    ".pytest-tmp*",
    ".ruff-cache*",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "coverage",
    "htmlcov",
    "dist",
    "build",
    "logs",
    "uploads",
    "qdrant_storage",
    ".cache",
    ".parcel-cache",
    "*.egg-info",
)

EXCLUDED_PATH_PREFIXES = (
    ".git/",
    ".agent-private/",
    "docs/ai/generated/",
)

AUTHORITATIVE_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".python-version",
    "docs/ai/RUNTIME_CONTRACT.md",
    "docs/ai/ENGINEERING_RULES.md",
    "docs/ai/TESTING.md",
    "docs/ai/TESTING_OPTIMIZED.md",
    "docs/ai/WORKFLOW.md",
)
AUTHORITATIVE_PREFIXES = (".claude/rules/",)
HISTORY_PATHS = (
    "docs/ai/memory/HISTORY.md",
    ".agent-private/HANDOFF.md",
    ".agent-private/CHANGE_HISTORY.jsonl",
)
HISTORY_PREFIXES = (
    "docs/ai/memory/handoffs/",
    "docs/ai/tasks/archive/",
    "docs/ai/archive/",
)
TASK_PREFIXES = ("docs/ai/tasks/",)
SOURCE_CLASSES = ("authoritative", "task", "history", "source")


def excluded_dir(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDED_DIR_PATTERNS)


def forbidden_path(rel: str) -> bool:
    posix = rel.replace(os.sep, "/")
    if posix.startswith("./"):
        posix = posix[2:]
    if posix.startswith(EXCLUDED_PATH_PREFIXES):
        return True
    return any(excluded_dir(part) for part in posix.split("/")[:-1])


def indexable_path(rel: str) -> bool:
    if forbidden_path(rel):
        return False
    name = rel.rsplit("/", 1)[-1]
    if name in TEXT_NAMES:
        return True
    return Path(name).suffix.lower() in TEXT_EXTS


def classify_source(rel: str) -> str:
    posix = rel.replace(os.sep, "/")
    if posix in AUTHORITATIVE_PATHS or posix.startswith(AUTHORITATIVE_PREFIXES):
        return "authoritative"
    if posix in HISTORY_PATHS or posix.startswith(HISTORY_PREFIXES):
        return "history"
    if posix.startswith(TASK_PREFIXES):
        return "task"
    return "source"


def _git_candidates(root: Path) -> list[str] | None:
    """Return Git-visible files only when *root itself* is the repository root.

    `git` walks parent directories looking for `.git`. That is useful normally,
    but dangerous for temporary test fixtures created inside a real checkout:
    a non-repository fixture can accidentally inherit the parent repository and
    receive paths that are relative to the parent instead of the fixture. In
    that case we must fall back to a bounded filesystem walk of the fixture.
    """
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    if top.returncode != 0:
        return None
    try:
        git_root = Path(top.stdout.strip()).resolve()
        requested_root = root.resolve()
    except OSError:
        return None
    if git_root != requested_root:
        return None

    try:
        completed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    raw = completed.stdout.decode("utf-8", errors="replace")
    return [entry for entry in raw.split("\0") if entry]


def _walk_candidates(root: Path) -> list[str]:
    if not root.exists():
        return []
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not excluded_dir(name))
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix()
        if rel_dir != "." and forbidden_path(rel_dir + "/x"):
            dirnames[:] = []
            continue
        for filename in filenames:
            found.append((current / filename).relative_to(root).as_posix())
    return found


def enumerate_sources(root: Path, use_git: bool = True) -> list[str]:
    """Return sorted tracked+untracked repository source, excluding private/cache/generated trees."""
    candidates = _git_candidates(root) if use_git else None
    if candidates is None:
        candidates = _walk_candidates(root)

    seen: set[str] = set()
    for rel in candidates:
        if rel in seen or not indexable_path(rel):
            continue
        path = root / rel
        try:
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        seen.add(rel)
    return sorted(seen)


def forbidden_indexed_paths(paths: Iterable[str]) -> list[str]:
    return sorted({rel for rel in paths if forbidden_path(rel)})
