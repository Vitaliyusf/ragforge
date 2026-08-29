#!/usr/bin/env python3
"""RAGForge Claude Code bootstrap + exploration gate.

This script has two roles:

1. Hook mode (``pre`` / ``post``): tiny, deterministic state enforcement for
   Claude Code's PreToolUse/PostToolUse lifecycle.
2. Bootstrap mode: a normal tool command Claude runs explicitly. It queries the
   existing Repo Brain, prints a compact source-oriented ownership packet, and
   writes session-scoped state that the PostToolUse hook can mark ready.

Why this shape:
- CLAUDE.md/AGENTS.md are instructions, not deterministic enforcement.
- PreToolUse can block a tool call; PostToolUse only fires after success.
- UserPromptSubmit context injection is intentionally NOT used because Windows
  / VS Code reports show stdin/additionalContext can be unreliable. The packet
  is instead ordinary tool output Claude necessarily sees.
- Brain v4 core/schema are not modified. The bootstrap compensates for active
  task markdown dominating Top-K by querying without the literal task id and
  by filtering/diversifying the final packet.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

TASK_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+[A-Z0-9]*\b")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_./+-]{2,}")
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
DOC_SUFFIXES = {".md", ".json", ".yml", ".yaml", ".toml"}
MAX_PRIMARY_RESULTS_PER_PATH = 2
MAX_PACKET_RESULTS = 12
MAX_PACKET_CHARS = 9000
MAX_EXCERPT_CHARS = 650
MAX_SOURCE_READ_LINES = 250

STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "only", "when", "where", "what",
    "should", "must", "task", "goal", "phase", "depends", "required", "current", "existing", "using",
    "used", "does", "not", "without", "after", "before", "then", "once", "full", "make", "keep", "clear",
    "real", "data", "show", "more", "less", "each", "every", "while", "acceptance", "criteria", "branch",
    "scope", "stop", "start", "replace", "default", "example", "implementation", "behavior", "behaviour",
    "support", "supported", "component", "components",
}
ALWAYS_USEFUL = {
    "files", "file", "frontend", "backend", "rag", "chat", "eval", "metrics", "memory", "gateway",
    "embedding", "vector", "document", "documents", "pipeline", "ingestion", "reindex", "rerun", "delete",
    "upload", "search", "filter", "sort", "table", "drawer", "bulk", "status", "review", "activity",
    "hooks", "tests", "test", "service", "router", "context", "retrieval", "runtime", "agent",
}

# Exact bounded Git inspection that is safe before bootstrap.
ALLOWED_GIT_PREFIXES = (
    "git status --short",
    "git branch --show-current",
    "git rev-parse HEAD",
    "git worktree list",
    "git diff --check",
    "git diff --stat",
)

# Recovery-only Brain commands allowed while the gate is closed.
BRAIN_RECOVERY_RE = re.compile(
    r"(?:^|[;&|]\s*)(?:py\s+-3\.12\s+|python\s+)scripts[/\\]ai[/\\]brain\.py\s+"
    r"(?:status|doctor|sync)(?:\s|$)",
    re.IGNORECASE,
)

BOOTSTRAP_MARKER = "repo-bootstrap.py"


def _stdout_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _project_root(data: dict[str, Any] | None = None) -> Path:
    data = data or {}
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or str(data.get("cwd") or os.getcwd())
    return Path(raw).resolve()


def _safe_session_id(value: Any) -> str:
    raw = str(value or "unknown-session")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", raw)
    return safe[:180] or "unknown-session"


def _state_dir(root: Path) -> Path:
    path = root / ".agent-private" / "claude-bootstrap"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(root: Path, session_id: str) -> Path:
    return _state_dir(root) / f"{_safe_session_id(session_id)}.json"


def _load_state(root: Path, session_id: str) -> dict[str, Any]:
    path = _state_path(root, session_id)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_state(root: Path, session_id: str, state: dict[str, Any]) -> None:
    path = _state_path(root, session_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/")


def _relative_to_root(root: Path, value: str | Path) -> str | None:
    try:
        p = Path(value)
        if not p.is_absolute():
            p = root / p
        rel = p.resolve().relative_to(root.resolve())
        return rel.as_posix()
    except Exception:
        return None


def _task_id_from_path(path: str) -> str | None:
    normalized = _normalize_path(path)
    match = re.search(r"(?:^|/)docs/ai/tasks/([A-Z][A-Z0-9-]*-\d+[A-Z0-9]*)\.md$", normalized, re.I)
    return match.group(1).upper() if match else None


def _find_task_spec(root: Path, task_id: str | None) -> Path | None:
    if not task_id or not TASK_ID_RE.fullmatch(task_id.upper()):
        return None
    candidate = root / "docs" / "ai" / "tasks" / f"{task_id.upper()}.md"
    return candidate if candidate.is_file() else None


def _extract_task_summary(spec_text: str) -> str:
    """Return generic retrieval material from any task spec.

    Do not hard-code one task's section names. Keep the first title, all
    headings, and a bounded amount of body text so path/symbol/behavior terms
    survive while metadata and prose cannot dominate the query.
    """
    lines = spec_text.splitlines()
    headings: list[str] = []
    body: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                headings.append(title)
            continue
        if not stripped:
            continue
        # Branch/phase/dependency metadata is useful to humans but weak for
        # implementation ownership retrieval.
        if re.match(r"^\*\*(?:branch|phase|depends on)\*\*\s*:", stripped, re.I):
            continue
        body.append(stripped)
        if len(" ".join(body)) >= 4200:
            break
    return (" ".join(headings[:24]) + " " + " ".join(body)).strip()[:6000]


def _normalized_keyword(token: str) -> str:
    token = token.strip("./:+-").lower()
    aliases = {"re-index": "reindex", "re-ingest": "reingest"}
    return aliases.get(token, token)


def _keywords(text: str) -> list[str]:
    words = [_normalized_keyword(w) for w in WORD_RE.findall(text)]
    return [w for w in words if w and (w in ALWAYS_USEFUL or (w not in STOPWORDS and len(w) >= 4))]


def build_brain_query(raw_query: str, task_id: str | None, spec_text: str = "") -> str:
    """Build lexical retrieval query without the literal task id.

    The existing Brain gives a strong authority boost to every chunk in a named
    task. The task spec is already read directly, so repeating the literal task
    id in retrieval wastes Top-K on markdown sections. We retain useful prefix
    words (FILES/LIST, CHAT, etc.) and task concepts, but remove the full id.
    """
    query_wo_id = TASK_ID_RE.sub(" ", raw_query or "")
    summary = TASK_ID_RE.sub(" ", _extract_task_summary(spec_text)) if spec_text else ""

    prefix_terms: list[str] = []
    if task_id:
        for part in task_id.upper().split("-"):
            low = part.lower()
            if low.isdigit() or len(low) < 3:
                continue
            prefix_terms.append(low)

    prompt_terms = _keywords(query_wo_id)
    spec_terms = _keywords(summary)
    counts = Counter(spec_terms)

    ordered: list[str] = []
    for token in [*prefix_terms, *prompt_terms]:
        if token not in ordered:
            ordered.append(token)
    for token, _count in counts.most_common():
        if token not in ordered:
            ordered.append(token)
    for token in spec_terms:
        if token not in ordered:
            ordered.append(token)

    if not ordered:
        ordered = ["repository", "source", "tests", "ownership"]
    return " ".join(ordered[:20])


def _brain_query(root: Path, query: str) -> tuple[list[dict[str, Any]], bool]:
    scripts = root / "scripts" / "ai"
    sys.path.insert(0, str(scripts))
    try:
        from brain_core import Brain  # type: ignore
    finally:
        try:
            sys.path.remove(str(scripts))
        except ValueError:
            pass

    brain = Brain(root)
    synced = False
    stale = brain.stale_paths(limit=1)
    if stale:
        brain.sync()
        synced = True
        remaining_stale = brain.stale_paths(limit=1)
        if remaining_stale:
            raise RuntimeError(f"Repo Brain remained stale after sync: {remaining_stale[0]}")
    results = brain.query(query, top=100)
    return [dict(item) for item in results], synced


def _is_source_evidence(item: dict[str, Any]) -> bool:
    path = str(item.get("path") or "").replace("\\", "/")
    source_class = str(item.get("source_class") or "")
    suffix = Path(path).suffix.lower()
    return source_class == "source" and suffix in SOURCE_SUFFIXES and path.startswith(("frontend/", "backend/", "tests/", "scripts/"))


def _is_test_path(path: str) -> bool:
    p = path.lower().replace("\\", "/")
    name = Path(p).name
    return "/tests/" in p or name.startswith("test_") or ".test." in name or ".spec." in name


def diversify_results(
    results: Iterable[dict[str, Any]],
    *,
    task_path: str | None = None,
    limit: int = MAX_PACKET_RESULTS,
) -> list[dict[str, Any]]:
    """Prefer source/test breadth and suppress repeated task markdown."""
    ranked = list(results)
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    path_counts: Counter[str] = Counter()
    task_norm = (task_path or "").replace("\\", "/")

    def usable(item: dict[str, Any]) -> bool:
        path = str(item.get("path") or "").replace("\\", "/")
        if not path:
            return False
        if task_norm and path == task_norm:
            return False
        # Other task specs/history are rarely useful for initial ownership.
        if path.startswith("docs/ai/tasks/"):
            return False
        return True

    def add_from(items: Iterable[dict[str, Any]]) -> None:
        for item in items:
            if len(selected) >= limit:
                return
            if not usable(item):
                continue
            cid = str(item.get("chunk_id") or f"{item.get('path')}:{item.get('start_line')}:{item.get('symbol')}")
            path = str(item.get("path") or "").replace("\\", "/")
            if cid in seen_ids or path_counts[path] >= MAX_PRIMARY_RESULTS_PER_PATH:
                continue
            selected.append(item)
            seen_ids.add(cid)
            path_counts[path] += 1

    # Implementation first, then tests, preserving Brain score order within
    # each tier. The packet is an ownership map: code tells Claude where the
    # behavior lives; tests then pin the contract.
    add_from(item for item in ranked if _is_source_evidence(item) and not _is_test_path(str(item.get("path") or "")))
    add_from(item for item in ranked if _is_source_evidence(item) and _is_test_path(str(item.get("path") or "")))
    # Then authoritative/source docs if capacity remains.
    add_from(item for item in ranked if not _is_source_evidence(item))
    return selected


def _render_packet(task_id: str | None, task_path: str | None, query: str, results: list[dict[str, Any]], synced: bool) -> str:
    lines = [
        "# Repo Brain bootstrap",
        "",
        f"Task: {task_id or 'ad-hoc'}",
        f"Task spec: {task_path or 'none'}",
        f"Brain query: {query}",
        f"Incremental sync: {'yes' if synced else 'no'}",
        "",
        "Use these paths first. Inspect the named symbol/range, not the whole file.",
        "Do not run repo-wide discovery unless this packet is insufficient; refine Brain once instead.",
        "",
    ]
    for i, item in enumerate(results, 1):
        path = str(item.get("path") or "")
        start = int(item.get("start_line") or 1)
        end = int(item.get("end_line") or start)
        symbol = str(item.get("symbol") or "<module>")
        reasons = ",".join(str(x) for x in item.get("reasons") or [])
        excerpt = re.sub(r"\s+", " ", str(item.get("excerpt") or "")).strip()[:MAX_EXCERPT_CHARS]
        lines.append(f"{i}. `{path}:{start}-{end}` — `{symbol}` [{reasons}]")
        if excerpt:
            lines.append(f"   {excerpt}")
    text = "\n".join(lines).rstrip() + "\n"
    return text[:MAX_PACKET_CHARS]


def _bootstrap(root: Path, session_id: str, task_id: str | None, raw_query: str) -> int:
    task_id = task_id.upper() if task_id else None
    task_spec = _find_task_spec(root, task_id)
    spec_text = task_spec.read_text(encoding="utf-8", errors="replace") if task_spec else ""
    if not raw_query and not spec_text:
        print("Bootstrap requires --task <TASK-ID> with an existing spec or --query <goal>.", file=sys.stderr)
        return 2

    query = build_brain_query(raw_query or spec_text, task_id, spec_text)
    try:
        results, synced = _brain_query(root, query)
    except Exception as exc:
        print(f"Repo Brain bootstrap failed: {exc}", file=sys.stderr)
        return 2

    task_rel = task_spec.relative_to(root).as_posix() if task_spec else None
    selected = diversify_results(results, task_path=task_rel)
    source_results = [item for item in selected if _is_source_evidence(item)]
    if not source_results:
        print(
            "Repo Brain returned no implementation/test evidence. Refine once with --query using concrete feature, symbol, endpoint, or behavior terms.",
            file=sys.stderr,
        )
        return 2

    packet = _render_packet(task_id, task_rel, query, selected, synced)
    state = _load_state(root, session_id)
    attempts = int(state.get("bootstrap_attempts") or 0) + 1
    state.update(
        {
            "status": "bootstrap_succeeded",
            "task_id": task_id,
            "task_spec": task_rel,
            "brain_query": query,
            "bootstrap_attempts": attempts,
            "result_count": len(selected),
            "source_result_count": len(source_results),
            "allowed_paths": [str(item.get("path") or "") for item in selected if str(item.get("path") or "")],
            "bootstrapped_at": time.time(),
        }
    )
    _write_state(root, session_id, state)
    print(packet, end="")
    return 0


def _deny(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _is_bootstrap_command(command: str) -> bool:
    low = command.lower().replace("\\", "/")
    return BOOTSTRAP_MARKER in low and re.search(r"\bbootstrap\b", low) is not None


def _session_arg_matches(command: str, session_id: str) -> bool:
    # Quoting can differ between Bash and PowerShell; a literal session id is
    # enough because Claude receives the exact id in the denial command.
    return session_id in command


def _git_command_allowed(command: str) -> bool:
    normalized = re.sub(r"\s+", " ", command.strip())
    # Allow chaining only these bounded git queries with && / ;.
    parts = [p.strip() for p in re.split(r"&&|;", normalized) if p.strip()]
    return bool(parts) and all(any(p.startswith(prefix) for prefix in ALLOWED_GIT_PREFIXES) for p in parts)


def _task_spec_read(data: dict[str, Any], root: Path) -> tuple[bool, str | None]:
    if str(data.get("tool_name") or "") != "Read":
        return False, None
    path = str((data.get("tool_input") or {}).get("file_path") or "")
    rel = _relative_to_root(root, path)
    if not rel:
        return False, None
    task_id = _task_id_from_path(rel)
    return bool(task_id), task_id


def _is_large_source(path: Path) -> bool:
    if path.suffix.lower() not in SOURCE_SUFFIXES or not path.is_file():
        return False
    try:
        # Stop as soon as the threshold is crossed instead of loading the file.
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for i, _ in enumerate(handle, 1):
                if i > MAX_SOURCE_READ_LINES:
                    return True
    except OSError:
        return False
    return False


def _block_large_native_read(data: dict[str, Any], root: Path) -> int | None:
    if str(data.get("tool_name") or "") != "Read":
        return None
    tool_input = data.get("tool_input") or {}
    path_raw = str(tool_input.get("file_path") or "")
    rel = _relative_to_root(root, path_raw)
    if not rel:
        return None
    path = root / rel
    if not _is_large_source(path):
        return None
    limit = tool_input.get("limit")
    if isinstance(limit, int) and 0 < limit <= MAX_SOURCE_READ_LINES:
        return None
    return _deny(
        f"Repo Bootstrap: `{rel}` is over {MAX_SOURCE_READ_LINES} lines. Read a symbol or bounded range first (Read limit <= {MAX_SOURCE_READ_LINES}); do not dump the whole file."
    )


def _simple_shell_whole_file(command: str, cwd: Path, root: Path) -> str | None:
    """Best-effort detector for common whole-file source dumps.

    This is an efficiency guard, not a security parser. Native Read is the
    authoritative structured path; this catches the exact waste pattern seen
    in practice (`cat File.jsx`, `Get-Content File.jsx`).
    """
    patterns = [
        r"(?:^|[;&|]\s*)cat\s+([^;&|]+)$",
        r"(?:^|[;&|]\s*)type\s+([^;&|]+)$",
        r"(?:^|[;&|]\s*)Get-Content\s+([^;&|]+)$",
    ]
    for pattern in patterns:
        m = re.search(pattern, command, re.IGNORECASE)
        if not m:
            continue
        arg = m.group(1).strip().strip('"\'')
        # Options make parsing ambiguous; don't false-positive bounded forms.
        if not arg or arg.startswith("-") or " " in arg and not Path(arg).suffix:
            continue
        p = Path(arg)
        if not p.is_absolute():
            p = cwd / p
        try:
            p = p.resolve()
            p.relative_to(root)
        except Exception:
            continue
        if _is_large_source(p):
            return p.relative_to(root).as_posix()
    return None


def _bootstrap_hint(root: Path, session_id: str, state: dict[str, Any], task_id: str | None = None) -> str:
    task_id = task_id or state.get("task_id")
    script = root / ".claude" / "hooks" / "repo-bootstrap.py"
    if task_id:
        cmd = f'py -3.12 "{script}" bootstrap --session "{session_id}" --task "{task_id}"'
    else:
        cmd = f'py -3.12 "{script}" bootstrap --session "{session_id}" --query "<task goal in plain words>"'
    return (
        "Repo Bootstrap gate: source exploration/editing is blocked until one source-oriented Brain bootstrap succeeds. "
        f"Run exactly: {cmd}. Do not substitute a direct `brain.py query`; the wrapper removes task-id bias and diversifies source/test paths."
    )


def _pre_mode(data: dict[str, Any], root: Path, session_id: str) -> int:
    tool = str(data.get("tool_name") or "")
    tool_input = data.get("tool_input") or {}
    state = _load_state(root, session_id)

    # Reading a different task spec means a new task within the same Claude
    # session. Re-lock before that task begins; the task read itself is allowed.
    is_task_read, read_task_id = _task_spec_read(data, root)
    if is_task_read and read_task_id:
        if state.get("task_id") and state.get("task_id") != read_task_id:
            state = {
                "status": "pending",
                "task_id": read_task_id,
                "task_spec": f"docs/ai/tasks/{read_task_id}.md",
                "bootstrap_attempts": 0,
            }
            _write_state(root, session_id, state)
        elif not state:
            state = {
                "status": "pending",
                "task_id": read_task_id,
                "task_spec": f"docs/ai/tasks/{read_task_id}.md",
                "bootstrap_attempts": 0,
            }
            _write_state(root, session_id, state)
        return 0

    ready = state.get("status") == "ready"

    # Always keep the large whole-file guard active, even after bootstrap.
    if ready:
        blocked = _block_large_native_read(data, root)
        if blocked is not None:
            return blocked
        if tool in {"Bash", "PowerShell"}:
            command = str(tool_input.get("command") or "")
            cwd = Path(str(data.get("cwd") or root))
            rel = _simple_shell_whole_file(command, cwd, root)
            if rel:
                return _deny(
                    f"Repo Bootstrap: shell command would print all of large source file `{rel}`. Use native Read with a bounded range/symbol instead."
                )
        return 0

    # Before bootstrap: bounded Git state is fine.
    if tool in {"Bash", "PowerShell"}:
        command = str(tool_input.get("command") or "")
        if _git_command_allowed(command):
            return 0
        if BRAIN_RECOVERY_RE.search(command):
            return 0
        if _is_bootstrap_command(command):
            if not _session_arg_matches(command, session_id):
                return _deny("Repo Bootstrap: bootstrap command session id does not match the current Claude session.")
            return 0

    # Task specs are the only file reads allowed before bootstrap.
    if tool == "Read":
        path = str(tool_input.get("file_path") or "")
        rel = _relative_to_root(root, path)
        if rel and _task_id_from_path(rel):
            return 0

    return _deny(_bootstrap_hint(root, session_id, state))


def _post_mode(data: dict[str, Any], root: Path, session_id: str) -> int:
    tool = str(data.get("tool_name") or "")
    tool_input = data.get("tool_input") or {}
    state = _load_state(root, session_id)

    if tool == "Read":
        path = str(tool_input.get("file_path") or "")
        rel = _relative_to_root(root, path)
        task_id = _task_id_from_path(rel or "") if rel else None
        if task_id:
            # Record the task for the exact bootstrap hint. Reading the task
            # never opens the gate by itself.
            if state.get("task_id") != task_id:
                state = {
                    "status": "pending",
                    "task_id": task_id,
                    "task_spec": rel,
                    "bootstrap_attempts": 0,
                }
            else:
                state["task_spec"] = rel
            state["task_read_at"] = time.time()
            _write_state(root, session_id, state)
        return 0

    if tool in {"Bash", "PowerShell"}:
        command = str(tool_input.get("command") or "")
        if _is_bootstrap_command(command) and _session_arg_matches(command, session_id):
            # PostToolUse only fires after a successful tool call. Bootstrap
            # mode wrote `bootstrap_succeeded`; only then is the gate opened.
            state = _load_state(root, session_id)
            if state.get("status") == "bootstrap_succeeded":
                state["status"] = "ready"
                state["ready_at"] = time.time()
                _write_state(root, session_id, state)
        return 0

    return 0


def hook_main(mode: str) -> int:
    data = _read_stdin_json()
    root = _project_root(data)
    session_id = _safe_session_id(data.get("session_id"))
    if mode == "pre":
        return _pre_mode(data, root, session_id)
    if mode == "post":
        return _post_mode(data, root, session_id)
    print(f"Unknown hook mode: {mode}", file=sys.stderr)
    return 2


def main() -> int:
    _stdout_utf8()
    parser = argparse.ArgumentParser(description="RAGForge Claude Repo Bootstrap")
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("pre")
    sub.add_parser("post")
    boot = sub.add_parser("bootstrap")
    boot.add_argument("--session", required=True)
    boot.add_argument("--task")
    boot.add_argument("--query", default="")
    args = parser.parse_args()

    if args.mode in {"pre", "post"}:
        return hook_main(args.mode)
    if args.mode == "bootstrap":
        root = _project_root({})
        return _bootstrap(root, _safe_session_id(args.session), args.task, args.query)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
