#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "docs" / "ai" / "memory"
PRIVATE = ROOT / ".agent-private"

ID_RE = re.compile(r"^(DEC|CAP|CON)-\d{3,}$")
SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "bearer": re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}"),
}

STRUCTURED = [
    ("SERVICES.json", "services", False),
    ("CAPABILITIES.json", "capabilities", True),
    ("CONTRACTS.json", "contracts", True),
    ("DECISIONS.json", "decisions", True),
]

def git_ignored(path: str) -> bool:
    try:
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0
    except Exception:
        return False

def scan_secrets(path: Path, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"{path.relative_to(ROOT)}: possible {name}")

def main() -> int:
    errors: list[str] = []
    seen: dict[str, str] = {}

    # Operational memory must not live in public tracked memory.
    forbidden_public = ["HANDOFF.md", "CHANGE_HISTORY.jsonl", "BUGS.json", "TECH_DEBT.json", "FAILED_APPROACHES.json"]
    for name in forbidden_public:
        if (PUBLIC / name).exists():
            errors.append(f"public memory contains operational/private file: docs/ai/memory/{name}")

    # Scan all public AI docs/memory/instructions for obvious secrets.
    for base in [ROOT / "AGENTS.md", ROOT / "CLAUDE.md", ROOT / "docs" / "ai"]:
        if base.is_file():
            scan_secrets(base, errors)
        elif base.exists():
            for path in base.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".md",".json",".jsonl",".txt",".py",".yml",".yaml"}:
                    if "generated" not in path.parts:
                        scan_secrets(path, errors)

    for filename, key, require_id in STRUCTURED:
        path = PUBLIC / filename
        if not path.exists():
            errors.append(f"missing public memory file: {filename}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{filename}: invalid JSON: {exc}")
            continue
        rows = data.get(key, [])
        if not isinstance(rows, list):
            errors.append(f"{filename}: `{key}` must be a list")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"{filename}[{index}]: object required")
                continue
            rid = row.get("id")
            if require_id and rid:
                if not ID_RE.match(str(rid)):
                    errors.append(f"{filename}[{index}]: invalid public memory id {rid}")
                if rid in seen:
                    errors.append(f"duplicate id {rid}: {seen[rid]} and {filename}")
                seen[rid] = filename
            for field in ("canonical_paths","evidence"):
                values = row.get(field)
                if not isinstance(values, list):
                    continue
                for value in values:
                    if isinstance(value, str) and value.startswith(("backend/","frontend/","docs/","scripts/")):
                        if Path(value).is_absolute() or ".." in Path(value).parts:
                            errors.append(f"{filename}:{rid or index}: unsafe path {value}")

    if PRIVATE.exists() and not git_ignored(".agent-private/"):
        errors.append(".agent-private/ exists but is NOT ignored by Git")

    generated = ROOT / "docs" / "ai" / "generated"
    if any(generated.glob("*.json")) and not git_ignored("docs/ai/generated/INDEX_META.json"):
        errors.append("generated AI index JSON exists but docs/ai/generated/*.json is not ignored by Git")

    if errors:
        print("AI memory/security validation FAILED")
        for error in errors:
            print("-", error)
        return 1

    print(f"AI memory/security validation OK ({len(seen)} public stable IDs)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
