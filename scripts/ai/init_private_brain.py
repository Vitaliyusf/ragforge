#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / ".agent-private"

def ignored() -> bool:
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-q", ".agent-private/"],
            cwd=ROOT,
            check=False,
        )
        return proc.returncode == 0
    except FileNotFoundError:
        return False

def main() -> int:
    if not ignored():
        print("REFUSING: .agent-private/ is not ignored by Git.")
        print("Add this line to the repository .gitignore first:")
        print("/.agent-private/")
        return 2

    PRIVATE.mkdir(parents=True, exist_ok=True)

    files = {
        "HANDOFF.md": "# Latest Private Handoff\n\nNo active handoff recorded.\n",
        "CHANGE_HISTORY.jsonl": "",
        "BUGS.json": {"schema_version": 1, "bugs": []},
        "TECH_DEBT.json": {"schema_version": 1, "items": []},
        "FAILED_APPROACHES.json": {"schema_version": 1, "approaches": []},
    }
    for name, value in files.items():
        path = PRIVATE / name
        if path.exists():
            continue
        if isinstance(value, str):
            path.write_text(value, encoding="utf-8")
        else:
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    print(f"Private agent memory ready: {PRIVATE}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
