#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain_core import Brain, json_dump  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _print_results(results):
    for item in results:
        reasons = ",".join(item["reasons"])
        private = " private" if item["is_private"] else ""
        print(
            f"[{float(item['score']):.4f}] {item['path']}:{item['start_line']}-{item['end_line']} "
            f"{item['symbol']} [{item['source_class']}{private}; {reasons}]"
        )
        print(f"  {item['excerpt']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="RAGForge Repo Brain v4")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="incrementally sync repository knowledge")
    sync.add_argument("--full", action="store_true", help="force a complete rebuild")

    sub.add_parser("status", help="show index freshness and counts")
    sub.add_parser("doctor", help="validate SQLite/FTS5/integrity/freshness")

    query = sub.add_parser("query", help="retrieve relevant repository chunks")
    query.add_argument("query")
    query.add_argument("--top", type=int, default=20)
    query.add_argument("--json", action="store_true")
    query.add_argument("--public-only", action="store_true")

    context = sub.add_parser("context", help="emit a bounded evidence/context packet")
    context.add_argument("query")
    context.add_argument("--top", type=int, default=12)
    context.add_argument("--budget-chars", type=int, default=12000)
    context.add_argument("--public-only", action="store_true")

    args = parser.parse_args()
    brain = Brain(ROOT)

    if args.command == "sync":
        result = brain.sync(full=args.full)
        print(json_dump(result))
        return 0
    if args.command == "status":
        status = brain.status()
        print(json_dump(status))
        return 1 if status.get("stale") else 0
    if args.command == "doctor":
        ok, details = brain.doctor()
        print(json_dump(details))
        print("Brain doctor:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    if args.command == "query":
        results = brain.query(args.query, top=args.top, public_only=args.public_only)
        if args.json:
            print(json_dump(results))
        else:
            _print_results(results)
        return 0 if results else 2
    if args.command == "context":
        packet = brain.context(args.query, top=args.top, budget_chars=args.budget_chars, public_only=args.public_only)
        print(packet)
        return 0 if packet else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
