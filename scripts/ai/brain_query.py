#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "docs" / "ai" / "memory"
PRIVATE = ROOT / ".agent-private"
GENERATED = ROOT / "docs" / "ai" / "generated"
MAX_QUERY_CHARS = 500

STOP = {"the","a","an","and","or","to","of","in","for","is","it","on","with","this","that","אני","את","של","זה","אם","על","עם","לא"}

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

def search_memory(directory: Path, query_tokens: list[str], bonus: float, results: list[tuple[float, str, str]]) -> None:
    if not directory.exists():
        return
    for path in sorted(directory.glob("*")):
        if not path.is_file():
            continue
        if path.suffix == ".json":
            for row in records(path):
                text = flatten(row)
                s = score(query_tokens, text)
                if s:
                    label = row.get("id") or row.get("name") or row.get("title") or "record"
                    results.append((s + bonus, f"{path.relative_to(ROOT)}::{label}", text[:700]))
        elif path.suffix in {".md", ".jsonl"}:
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                s = score(query_tokens, line)
                if s:
                    results.append((s + bonus, f"{path.relative_to(ROOT)}:{line_no}", line[:700]))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    query = args.query[:MAX_QUERY_CHARS]
    q = tokens(query)
    if not q:
        print("No useful query tokens.")
        return 2

    results: list[tuple[float, str, str]] = []
    search_memory(PUBLIC, q, 2.0, results)
    search_memory(PRIVATE, q, 2.5, results)

    for name in ["SYMBOL_INDEX.json","ROUTE_INDEX.json","CONFIG_INDEX.json","FILE_INDEX.json","FRONTEND_INDEX.json"]:
        path = GENERATED / name
        if not path.exists():
            continue
        for row in records(path):
            text = flatten(row)
            s = score(q, text)
            if s:
                label = row.get("qualname") or row.get("name") or row.get("route") or row.get("key") or row.get("path") or "record"
                results.append((s, f"{path.relative_to(ROOT)}::{label}", text[:700]))

    results.sort(key=lambda x: (-x[0], x[1]))
    for s, where, excerpt in results[:max(1, min(args.top, 100))]:
        print(f"[{s:.1f}] {where}\n  {excerpt}")
    if not results:
        print("No brain/index matches. Use targeted source search next.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
