#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _git_ignored(rel: str) -> bool:
    try:
        return subprocess.run(
            ["git", "check-ignore", "-q", "--", rel],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
    except OSError:
        return False


def main() -> int:
    errors: list[str] = []
    agents = ROOT / "AGENTS.md"
    claude = ROOT / "CLAUDE.md"
    rules = ROOT / ".claude" / "rules"

    if not agents.exists():
        errors.append("missing AGENTS.md")
    else:
        text = agents.read_text(encoding="utf-8")
        lines = text.splitlines()
        if len(lines) > 200:
            errors.append(f"AGENTS.md too large for always-on context: {len(lines)} lines > 200")
        if len(text.encode("utf-8")) > 8000:
            errors.append(f"AGENTS.md too large for always-on context: {len(text.encode('utf-8'))} bytes > 8000")
        for required in ("docs/ai/RUNTIME_CONTRACT.md", "scripts/ai/brain.py", "docs/ai/memory/MEMORY_PROTOCOL.md"):
            if required not in text:
                errors.append(f"AGENTS.md missing navigation pointer: {required}")

    if not claude.exists():
        errors.append("missing CLAUDE.md")
    else:
        text = claude.read_text(encoding="utf-8")
        if "@AGENTS.md" not in text:
            errors.append("CLAUDE.md must import @AGENTS.md")
        if len(text.splitlines()) > 80:
            errors.append("CLAUDE.md should remain a small adapter")

    if _git_ignored("CLAUDE.md"):
        errors.append("CLAUDE.md is Git-ignored; shared Claude project instructions must be tracked")

    legacy_nested = ["backend/CLAUDE.md", "backend/rag/CLAUDE.md", "frontend/CLAUDE.md"]
    present_legacy = [rel for rel in legacy_nested if (ROOT / rel).exists()]
    if present_legacy:
        errors.append(
            "legacy nested CLAUDE.md files conflict with .claude/rules: " + ", ".join(present_legacy)
        )

    expected_rules = {"backend.md", "rag.md", "frontend.md", "tests.md", "agent-memory.md"}
    actual = {p.name for p in rules.glob("*.md")} if rules.exists() else set()
    missing = sorted(expected_rules - actual)
    if missing:
        errors.append("missing Claude path rules: " + ", ".join(missing))
    for rule in sorted(expected_rules):
        rel = f".claude/rules/{rule}"
        if (ROOT / rel).exists() and _git_ignored(rel):
            errors.append(f"{rel} is Git-ignored; shared path rules must be tracked")

    for path in rules.glob("*.md") if rules.exists() else []:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\npaths:\n" not in text[:500]:
            errors.append(f"{path.relative_to(ROOT)} must use path-scoped `paths` frontmatter")

    brain = ROOT / "scripts" / "ai" / "brain.py"
    if not brain.exists():
        errors.append("missing scripts/ai/brain.py")
    else:
        proc = subprocess.run(
            [sys.executable, str(brain), "doctor"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if proc.returncode != 0:
            errors.append("brain doctor failed: " + (proc.stdout or "").strip()[-1000:])

    if errors:
        print("Agent context validation: FAIL")
        for error in errors:
            print("-", error)
        return 1
    print("Agent context validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
