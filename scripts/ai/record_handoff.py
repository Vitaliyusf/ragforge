#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / ".agent-private"

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}"),
]

def git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None

def is_private_ignored() -> bool:
    try:
        return subprocess.run(["git", "check-ignore", "-q", ".agent-private/"], cwd=ROOT).returncode == 0
    except Exception:
        return False

def redact(value: str, max_len: int = 2000) -> str:
    value = value.replace("\x00", "")
    value = "".join(ch for ch in value if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    value = value[:max_len]
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED_SECRET]", value)
    return value

def safe_repo_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"file path must be repository-relative: {value}")
    return value.replace("\\", "/")[:500]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=["codex","claude","human"], required=True)
    parser.add_argument("--task", default=None)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--result", choices=["completed","partial","blocked"], default="completed")
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--tests", nargs="*", default=[])
    parser.add_argument("--memory-ids", nargs="*", default=[])
    parser.add_argument("--unresolved", nargs="*", default=[])
    parser.add_argument("--next", dest="next_step", default="")
    parser.add_argument("--safe-for-commit", choices=["yes","no"], default="no")
    args = parser.parse_args()

    if not is_private_ignored():
        print("REFUSING: .agent-private/ is not ignored by Git. Run init_private_brain.py after updating .gitignore.")
        return 2

    PRIVATE.mkdir(parents=True, exist_ok=True)

    files = [safe_repo_path(x) for x in args.files]
    tests = [redact(x, 500) for x in args.tests]
    memory_ids = [redact(x, 100) for x in args.memory_ids]
    unresolved = [redact(x, 500) for x in args.unresolved]
    summary = redact(args.summary, 2000)
    next_step = redact(args.next_step, 1000)

    branch = git("branch", "--show-current")
    sha = git("rev-parse", "HEAD")
    now = datetime.now(timezone.utc).isoformat()

    row = {
        "ts": now,
        "agent": args.agent,
        "task": redact(args.task or "", 100) or None,
        "branch": redact(branch or "unknown", 200),
        "head": sha,
        "summary": summary,
        "files": files,
        "tests": tests,
        "memory_ids": memory_ids,
        "result": args.result,
    }

    history = PRIVATE / "CHANGE_HISTORY.jsonl"
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {x}" for x in items) if items else "- None"

    handoff = f"""# Latest Private Handoff

- Task: {row['task'] or 'untracked'}
- Agent: {args.agent}
- Branch: {row['branch']}
- HEAD: {sha or 'unknown'}
- Status: {args.result}
- Timestamp: {now}
- Safe for manual commit: {args.safe_for_commit}

## What changed
{summary}

## Files touched
{bullets([f'`{x}`' for x in files])}

## Tests/checks
{bullets(tests)}

## Memory records
{bullets(memory_ids)}

## Unresolved
{bullets(unresolved)}

## Next recommended step
{next_step or 'None recorded'}
"""
    (PRIVATE / "HANDOFF.md").write_text(handoff, encoding="utf-8")
    print("Recorded private handoff/history.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
