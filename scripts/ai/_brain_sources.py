#!/usr/bin/env python3
"""Shared source-enumeration and source-authority rules for the repo brain.

One module owns three facts so the rebuilder, the query tool and the validator
cannot drift apart:

* which files are repository source at all (Git-first enumeration);
* which directories are never source (task-local caches, venvs, generated output);
* how an indexed path is classified for retrieval authority.
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Iterable

MAX_FILE_BYTES = 2 * 1024 * 1024

TEXT_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml", ".toml", ".md"}
# Extension-less files that are still authoritative repository source.
TEXT_NAMES = {".python-version"}

# Directory-name patterns that are never repository source. Patterns, not exact
# names: task-local variants such as `.uv-cache-safe01-memory` kept appearing at
# the repository root and exploding rebuild cost.
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

# Derived/private trees excluded even if accidentally tracked or unignored.
EXCLUDED_PATH_PREFIXES = (
    ".git/",
    ".agent-private/",
    "docs/ai/generated/",
)

AUTHORITATIVE_PATHS = (
    "AGENTS.md",
    ".python-version",
    "docs/ai/RUNTIME_CONTRACT.md",
    "docs/ai/ENGINEERING_RULES.md",
    "docs/ai/TESTING.md",
    "docs/ai/TESTING_OPTIMIZED.md",
    "docs/ai/WORKFLOW.md",
)
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
    """True when a directory name matches a never-source pattern."""
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDED_DIR_PATTERNS)


def forbidden_path(rel: str) -> bool:
    """True when a repo-relative path must never appear in a generated index."""
    posix = rel.replace(os.sep, "/")
    if posix.startswith("./"):
        posix = posix[2:]
    if posix.startswith(EXCLUDED_PATH_PREFIXES):
        return True
    return any(excluded_dir(part) for part in posix.split("/")[:-1])


def indexable_path(rel: str) -> bool:
    """True when a repo-relative path is indexable repository source."""
    if forbidden_path(rel):
        return False
    name = rel.rsplit("/", 1)[-1]
    if name in TEXT_NAMES:
        return True
    suffix = Path(name).suffix.lower()
    return suffix in TEXT_EXTS


def classify_source(rel: str) -> str:
    """Bounded retrieval-authority class for a repo-relative path."""
    posix = rel.replace(os.sep, "/")
    if posix in AUTHORITATIVE_PATHS:
        return "authoritative"
    if posix in HISTORY_PATHS or posix.startswith(HISTORY_PREFIXES):
        return "history"
    if posix.startswith(TASK_PREFIXES):
        return "task"
    return "source"


def _git_candidates(root: Path) -> list[str] | None:
    """Repo-relative paths from Git, or None when Git enumeration is unavailable."""
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
    """Filesystem fallback that prunes never-source directories while walking."""
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
            rel = (current / filename).relative_to(root).as_posix()
            found.append(rel)
    return found


def enumerate_sources(root: Path, use_git: bool = True) -> list[str]:
    """Sorted, de-duplicated repo-relative source paths for brain indexing.

    Git enumeration wins when available: it already excludes ignored caches and
    never traverses node_modules or virtualenvs. Deleted files are dropped by the
    existence check, and untracked production source is kept so the brain can
    represent an uncommitted task worktree.

    There is no force-include list: what Git reports as repository source is what
    the brain indexes, so `.gitignore` and the index can never disagree about a
    tree such as `docs/ai`. The filesystem walk stays as a fallback for
    environments where Git enumeration is unavailable.
    """
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
    """Indexed paths that violate the cache/private/generated exclusion rules."""
    return sorted({rel for rel in paths if forbidden_path(rel)})
