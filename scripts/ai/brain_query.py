#!/usr/bin/env python3
"""Compatibility wrapper for the pre-v4 `brain_query.py` CLI and module API."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain_core import Brain  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MAX_QUERY_CHARS = 500
STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "for", "is", "it", "on", "with", "this", "that", "אני", "את", "של", "זה", "אם", "על", "עם", "לא"}


def tokens(text: str) -> list[str]:
    return [x for x in re.findall(r"[\w./:@+-]+", text.lower(), flags=re.UNICODE) if len(x) > 1 and x not in STOP]


def run_query(root: Path, query: str, top: int = 20) -> list[tuple[float, str, str]]:
    """Preserve the old test/helper API while delegating retrieval to Brain v4."""
    if not tokens(query[:MAX_QUERY_CHARS]):
        return []
    brain = Brain(root)
    results = brain.query(query[:MAX_QUERY_CHARS], top=top)
    return [
        (
            round(float(item["score"]) * 1000.0, 6),
            f"{item['path']}:{item['start_line']} [{item['source_class']}]",
            str(item["excerpt"]),
        )
        for item in results
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--public-only", action="store_true")
    args = parser.parse_args()

    if not tokens(args.query[:MAX_QUERY_CHARS]):
        print("No useful query tokens.")
        return 2

    results = Brain(ROOT).query(args.query[:MAX_QUERY_CHARS], top=args.top, public_only=args.public_only)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            reasons = ",".join(item["reasons"])
            print(
                f"[{float(item['score']):.4f}] {item['path']}:{item['start_line']}-{item['end_line']} "
                f"[{item['source_class']}; {reasons}]"
            )
            print(f"  {item['excerpt']}")
    if not results:
        print("No brain matches. Use targeted source search next.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
