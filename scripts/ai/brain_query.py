#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _brain_sources import classify_source  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MAX_QUERY_CHARS = 500

# Bounded retrieval precedence. Current authoritative runtime/tooling docs win
# over task specs and history; historical records stay reachable but are demoted
# so an old task's runtime text cannot outrank the canonical contract. The weight
# is multiplicative because a single dense history record (one JSONL line holding
# a whole run) otherwise accumulates more raw hits than a precise contract line.
CLASS_WEIGHT = {
    "authoritative": 1.5,
    "source": 1.0,
    "task": 1.0,
    "history": 0.5,
}
CLASS_BOOST = {
    "authoritative": 3.0,
    "source": 0.0,
    "task": 0.0,
    "history": -1.0,
}


def weigh(raw: float, source_class: str, extra: float = 0.0, weight: float | None = None) -> float:
    """Apply bounded source-authority precedence to a raw match score."""
    if weight is None:
        weight = CLASS_WEIGHT.get(source_class, 1.0)
    return raw * weight + CLASS_BOOST.get(source_class, 0.0) + extra
# A direct task-ID query must still surface that task's own spec.
TASK_ID_BOOST = 6.0
TASK_ID_WEIGHT = 2.0
TASK_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+[A-Z0-9]*\b")

STOP = {"the","a","an","and","or","to","of","in","for","is","it","on","with","this","that","אני","את","של","זה","אם","על","עם","לא"}

INDEX_FILES = ["SYMBOL_INDEX.json","ROUTE_INDEX.json","CONFIG_INDEX.json","FILE_INDEX.json","FRONTEND_INDEX.json"]


def tokens(text: str) -> list[str]:
    return [x for x in re.findall(r"[\w./:@+-]+", text.lower(), flags=re.UNICODE) if len(x) > 1 and x not in STOP]

def flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(str(k) + " " + flatten(v) for k, v in value.items())
    if isinstance(value, list):
        return " ".join(flatten(v) for v in value)
    return "" if value is None else str(value)

def score(query_tokens: list[str], text: str) -> float:
    low = text.lower()
    total = 0.0
    for token in query_tokens:
        count = low.count(token)
        if count:
            total += min(count, 5)
            if re.search(rf"\b{re.escape(token)}\b", low):
                total += 1.5
    return total

def records(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [{"_value": x} for x in data]
    if not isinstance(data, dict):
        return [{"_value": data}]
    lists = [(k, v) for k, v in data.items() if isinstance(v, list)]
    if lists:
        key, values = max(lists, key=lambda kv: len(kv[1]))
        return [{"_collection": key, **(x if isinstance(x, dict) else {"_value": x})} for x in values]
    return [data]

def search_memory(root: Path, directory: Path, query_tokens: list[str], base_bonus: float, results: list[tuple[float, str, str]]) -> None:
    if not directory.exists():
        return
    for path in sorted(directory.glob("*")):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        # History (HANDOFF.md, CHANGE_HISTORY.jsonl, handoffs/) stays reachable but demoted.
        source_class = classify_source(rel)
        if path.suffix == ".json":
            for row in records(path):
                text = flatten(row)
                s = score(query_tokens, text)
                if s:
                    label = row.get("id") or row.get("name") or row.get("title") or "record"
                    results.append((weigh(s, source_class, base_bonus), f"{rel}::{label}", text[:700]))
        elif path.suffix in {".md", ".jsonl"}:
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                s = score(query_tokens, line)
                if s:
                    results.append((weigh(s, source_class, base_bonus), f"{rel}:{line_no}", line[:700]))


def doc_sources(root: Path) -> list[Path]:
    """Authority-classified documents searched by content.

    `docs/ai/memory` is handled by `search_memory`, and `docs/ai/generated` is
    generated output that must never act as a content source.
    """
    found: list[Path] = []
    for candidate in [root / "AGENTS.md", root / ".python-version"]:
        if candidate.is_file():
            found.append(candidate)
    docs = root / "docs" / "ai"
    if docs.is_dir():
        for path in sorted(docs.rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            if rel.startswith(("docs/ai/generated/", "docs/ai/memory/")):
                continue
            found.append(path)
    return found


def search_docs(root: Path, query_tokens: list[str], query_task_ids: set[str], results: list[tuple[float, str, str]]) -> None:
    for path in doc_sources(root):
        rel = path.relative_to(root).as_posix()
        source_class = classify_source(rel)
        extra = 0.0
        weight: float | None = None
        # A directly named task owns its own semantics for that query, so it
        # outranks even the authoritative docs while the query names it.
        if source_class == "task" and any(tid in rel.upper() for tid in query_task_ids):
            extra = TASK_ID_BOOST
            weight = TASK_ID_WEIGHT
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            s = score(query_tokens, line)
            if s:
                results.append((weigh(s, source_class, extra, weight), f"{rel}:{line_no} [{source_class}]", line[:700]))


def run_query(root: Path, query: str, top: int = 20) -> list[tuple[float, str, str]]:
    query = query[:MAX_QUERY_CHARS]
    query_tokens = tokens(query)
    if not query_tokens:
        return []

    query_task_ids = set(TASK_ID_RE.findall(query.upper()))
    results: list[tuple[float, str, str]] = []
    search_memory(root, root / "docs" / "ai" / "memory", query_tokens, 2.0, results)
    search_memory(root, root / ".agent-private", query_tokens, 2.5, results)
    search_docs(root, query_tokens, query_task_ids, results)

    generated = root / "docs" / "ai" / "generated"
    for name in INDEX_FILES:
        path = generated / name
        if not path.exists():
            continue
        for row in records(path):
            text = flatten(row)
            s = score(query_tokens, text)
            if not s:
                continue
            label = row.get("qualname") or row.get("name") or row.get("route") or row.get("key") or row.get("path") or "record"
            row_path = row.get("path")
            row_class = classify_source(row_path) if isinstance(row_path, str) else "source"
            results.append((weigh(s, row_class), f"{path.relative_to(root).as_posix()}::{label}", text[:700]))

    results.sort(key=lambda x: (-x[0], x[1]))
    return results[:max(1, min(top, 100))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    if not tokens(args.query[:MAX_QUERY_CHARS]):
        print("No useful query tokens.")
        return 2

    results = run_query(ROOT, args.query, args.top)
    for s, where, excerpt in results:
        print(f"[{s:.1f}] {where}\n  {excerpt}")
    if not results:
        print("No brain/index matches. Use targeted source search next.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
