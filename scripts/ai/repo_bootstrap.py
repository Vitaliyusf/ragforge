#!/usr/bin/env python3
"""RAGForge source-oriented repository bootstrap.

Agent-neutral wrapper around Repo Brain v4.

For a named task it uses the task spec to build two complementary retrieval
queries (ownership/scope and required behavior), merges a wider candidate pool,
and re-ranks results toward explicit implementation/test ownership. The Repo
Brain core, schema, authority boosts, and graph behavior remain unchanged.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
AI_DIR = ROOT / "scripts" / "ai"
TASK_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+[A-Z0-9]*\b")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_./+-]{2,}")
CODE_SPAN_RE = re.compile(r"`([^`]+)`")
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
MAX_PRIMARY_RESULTS_PER_PATH = 2
DEFAULT_LIMIT = 12
MAX_PACKET_CHARS = 9000
MAX_EXCERPT_CHARS = 650

STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "only", "when",
    "where", "what", "should", "must", "task", "goal", "phase", "depends", "required",
    "current", "existing", "using", "used", "does", "not", "without", "after", "before",
    "then", "once", "full", "make", "keep", "clear", "real", "data", "show", "more",
    "less", "each", "every", "while", "acceptance", "criteria", "branch", "scope",
    "stop", "start", "replace", "default", "example", "implementation", "behavior",
    "behaviour", "support", "supported", "component", "components", "production",
    "files", "file", "code", "tests", "test", "unless", "remove", "ownership",
}

# Domain terms are intentionally not enough by themselves to win ranking; they
# help formulate queries, while the re-ranker below favors path/symbol matches.
DOMAIN_TERMS = {
    "frontend", "backend", "rag", "chat", "eval", "metrics", "memory", "gateway",
    "embedding", "vector", "document", "documents", "pipeline", "ingestion", "reindex",
    "rerun", "delete", "upload", "search", "filter", "sort", "table", "drawer", "bulk",
    "status", "review", "activity", "service", "router", "context", "retrieval", "runtime",
    "agent", "provider", "providers", "prompt", "registry", "schema", "typed", "control",
    "plane", "vllm", "model", "summary", "curation", "title", "execution", "telemetry",
    "decode", "validate", "invoke", "render", "plan", "rpc", "langchain", "dockerfile",
    "requirements",
}

GENERIC_PATH_PENALTIES = (
    "/core/errors.py",
    "/core/exception_handlers.py",
    "/cache/",
)


def _stdout_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _find_task_spec(task_id: str | None) -> Path | None:
    if not task_id:
        return None
    task_id = task_id.upper()
    if not TASK_ID_RE.fullmatch(task_id):
        return None
    path = ROOT / "docs" / "ai" / "tasks" / f"{task_id}.md"
    return path if path.is_file() else None


def _section(spec_text: str, heading: str) -> str:
    target = heading.strip().lower()
    lines = spec_text.splitlines()
    start: int | None = None
    level = 0
    body: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(#+)\s+(.*)$", line.strip())
        if match and match.group(2).strip().lower() == target:
            start = index + 1
            level = len(match.group(1))
            break
    if start is None:
        return ""
    for line in lines[start:]:
        match = re.match(r"^(#+)\s+(.*)$", line.strip())
        if match and len(match.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body).strip()


def _extract_task_summary(spec_text: str) -> str:
    parts = []
    for heading in ("Goal", "Primary scope", "Required behavior", "Local refactor budget", "Validation"):
        body = _section(spec_text, heading)
        if body:
            parts.append(f"{heading}: {body}")
    return "\n".join(parts)[:8000]


def _normalize_keyword(token: str) -> str:
    token = token.strip("./:+-`*()[]{}<>,.;\"'").lower()
    return {
        "re-index": "reindex",
        "re-ingest": "reingest",
        "llmservice": "llm_service",
        "promptregistry": "prompt_registry",
    }.get(token, token)


def _keywords(text: str) -> list[str]:
    words = [_normalize_keyword(w) for w in WORD_RE.findall(text)]
    return [
        w for w in words
        if w and (w in DOMAIN_TERMS or (w not in STOPWORDS and len(w) >= 4))
    ]


def _scope_anchors(spec_text: str) -> list[str]:
    """Extract high-value owner hints from Primary scope and code spans."""
    scope = _section(spec_text, "Primary scope")
    anchors: list[str] = []

    # Explicit code spans/path-like values carry the strongest ownership signal.
    for raw in CODE_SPAN_RE.findall(scope):
        value = raw.strip()
        if not value:
            continue
        p = value.replace("\\", "/")
        name = Path(p).name
        stem = Path(name).stem
        for candidate in (p, name, stem):
            low = _normalize_keyword(candidate)
            if low and low not in anchors:
                anchors.append(low)

    # Bullet text often names an owner even when no exact path is given.
    for line in scope.splitlines():
        stripped = re.sub(r"^[\s*+-]+", "", line).strip()
        for token in _keywords(stripped):
            if token not in anchors:
                anchors.append(token)

    # Preserve useful compound names before generic tokens.
    compound_text = " ".join(CODE_SPAN_RE.findall(spec_text))
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]+", compound_text):
        low = _normalize_keyword(token)
        if "_" in low and low not in anchors:
            anchors.insert(0, low)
    return anchors[:24]


def _behavior_terms(spec_text: str) -> list[str]:
    behavior = _section(spec_text, "Required behavior")
    terms: list[str] = []
    for token in _keywords(behavior):
        if token not in terms:
            terms.append(token)
    return terms[:24]


def _prefix_terms(task_id: str | None) -> list[str]:
    if not task_id:
        return []
    out: list[str] = []
    for part in task_id.upper().split("-"):
        low = part.lower()
        if not low.isdigit() and len(low) >= 3 and low not in out:
            out.append(low)
    return out


def build_brain_queries(raw_query: str, task_id: str | None, spec_text: str = "") -> tuple[str, str, list[str]]:
    """Return ownership query, behavior query, and high-value anchors."""
    raw_wo_id = TASK_ID_RE.sub(" ", raw_query or "")
    prompt_terms = _keywords(raw_wo_id)
    anchors = _scope_anchors(spec_text)
    behavior = _behavior_terms(spec_text)
    prefixes = _prefix_terms(task_id)

    ownership: list[str] = []
    for token in [*anchors, *prefixes, *prompt_terms]:
        if token not in ownership:
            ownership.append(token)

    behavior_query: list[str] = []
    for token in [*prompt_terms, *behavior, *anchors[:8], *prefixes]:
        if token not in behavior_query:
            behavior_query.append(token)

    if not ownership:
        ownership = ["repository", "source", "ownership"]
    if not behavior_query:
        behavior_query = ownership.copy()

    return " ".join(ownership[:18]), " ".join(behavior_query[:18]), anchors


def build_brain_query(raw_query: str, task_id: str | None, spec_text: str = "") -> str:
    """Compatibility helper used by older tests/callers; returns ownership query."""
    return build_brain_queries(raw_query, task_id, spec_text)[0]


def _load_brain():
    sys.path.insert(0, str(AI_DIR))
    try:
        from brain_core import Brain  # type: ignore
        return Brain
    finally:
        try:
            sys.path.remove(str(AI_DIR))
        except ValueError:
            pass


def _brain_queries(queries: Iterable[str]) -> tuple[list[dict[str, Any]], bool]:
    Brain = _load_brain()
    brain = Brain(ROOT)
    synced = False
    stale = brain.stale_paths(limit=1)
    if stale:
        brain.sync()
        synced = True
        remaining = brain.stale_paths(limit=1)
        if remaining:
            raise RuntimeError(f"Repo Brain remained stale after sync: {remaining[0]}")

    merged: dict[str, dict[str, Any]] = {}
    for query_index, query in enumerate(queries):
        if not query.strip():
            continue
        for rank, raw in enumerate(brain.query(query, top=100), 1):
            item = dict(raw)
            cid = str(item.get("chunk_id") or f"{item.get('path')}:{item.get('start_line')}:{item.get('symbol')}")
            existing = merged.get(cid)
            contribution = 1.0 / (8.0 + rank) + (0.020 if query_index == 0 else 0.0)
            if existing is None:
                item["bootstrap_retrieval_score"] = contribution
                item["bootstrap_query_hits"] = [query_index]
                merged[cid] = item
            else:
                existing["bootstrap_retrieval_score"] = float(existing.get("bootstrap_retrieval_score", 0.0)) + contribution
                hits = list(existing.get("bootstrap_query_hits", []))
                if query_index not in hits:
                    hits.append(query_index)
                existing["bootstrap_query_hits"] = hits
    return list(merged.values()), synced


def _is_test_path(path: str) -> bool:
    p = path.lower().replace("\\", "/")
    name = Path(p).name
    return "/tests/" in p or name.startswith("test_") or ".test." in name or ".spec." in name


def _is_source(item: dict[str, Any]) -> bool:
    path = str(item.get("path") or "").replace("\\", "/")
    return (
        str(item.get("source_class") or "") == "source"
        and Path(path).suffix.lower() in SOURCE_SUFFIXES
        and path.startswith(("backend/", "frontend/", "tests/", "scripts/"))
    )


def _is_product_source(item: dict[str, Any]) -> bool:
    path = str(item.get("path") or "").replace("\\", "/")
    return _is_source(item) and path.startswith(("backend/", "frontend/"))


def _is_tooling_source(item: dict[str, Any]) -> bool:
    path = str(item.get("path") or "").replace("\\", "/")
    return _is_source(item) and path.startswith(("scripts/", "tests/"))


def _candidate_text(item: dict[str, Any]) -> tuple[str, str, str]:
    path = str(item.get("path") or "").replace("\\", "/").lower()
    symbol = str(item.get("symbol") or "").lower()
    excerpt = str(item.get("excerpt") or "").lower()
    return path, symbol, excerpt


def _token_overlap_score(text: str, terms: Iterable[str], weight: float) -> float:
    score = 0.0
    for term in terms:
        term = term.lower()
        if term and term in text:
            score += weight
    return score


def _rerank_score(item: dict[str, Any], *, anchors: list[str], query_terms: list[str]) -> float:
    path, symbol, excerpt = _candidate_text(item)
    score = float(item.get("bootstrap_retrieval_score", 0.0)) * 8.0

    # Explicit task-scope anchors should dominate generic lexical matches.
    score += _token_overlap_score(path, anchors, 5.0)
    score += _token_overlap_score(symbol, anchors, 4.0)
    score += _token_overlap_score(excerpt, anchors, 0.8)

    # User/task behavior terms are secondary ownership evidence.
    score += _token_overlap_score(path, query_terms, 1.5)
    score += _token_overlap_score(symbol, query_terms, 1.2)
    score += _token_overlap_score(excerpt, query_terms, 0.18)

    if _is_test_path(path):
        score += 0.35
    if "/services/" in path or "/llm/" in path or "/schemas/" in path:
        score += 0.30
    if any(fragment in path for fragment in GENERIC_PATH_PENALTIES):
        # Generic infrastructure should not crowd out named scope unless it also
        # has an explicit anchor hit.
        has_anchor = any(anchor in path or anchor in symbol for anchor in anchors)
        if not has_anchor:
            score -= 2.5
    return score


def diversify_results(
    results: Iterable[dict[str, Any]],
    *,
    task_path: str | None = None,
    limit: int = DEFAULT_LIMIT,
    anchors: list[str] | None = None,
    query_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    anchors = anchors or []
    query_terms = query_terms or []
    ranked = sorted(
        list(results),
        key=lambda item: (
            -_rerank_score(item, anchors=anchors, query_terms=query_terms),
            str(item.get("path") or ""),
            int(item.get("start_line") or 0),
        ),
    )
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    path_counts: Counter[str] = Counter()
    task_norm = (task_path or "").replace("\\", "/")

    def usable(item: dict[str, Any]) -> bool:
        path = str(item.get("path") or "").replace("\\", "/")
        if not path:
            return False
        if task_norm and path == task_norm:
            return False
        if path.startswith("docs/ai/tasks/"):
            return False
        return True

    def add(items: Iterable[dict[str, Any]]) -> None:
        for item in items:
            if len(selected) >= limit:
                return
            if not usable(item):
                continue
            path = str(item.get("path") or "").replace("\\", "/")
            key = str(item.get("chunk_id") or f"{path}:{item.get('start_line')}:{item.get('symbol')}")
            if key in seen or path_counts[path] >= MAX_PRIMARY_RESULTS_PER_PATH:
                continue
            selected.append(item)
            seen.add(key)
            path_counts[path] += 1

    add(item for item in ranked if _is_product_source(item) and not _is_test_path(str(item.get("path") or "")))
    add(item for item in ranked if _is_product_source(item) and _is_test_path(str(item.get("path") or "")))
    add(item for item in ranked if not _is_source(item))
    add(item for item in ranked if _is_tooling_source(item))
    return selected


def render_packet(
    task_id: str | None,
    task_path: str | None,
    ownership_query: str,
    behavior_query: str,
    results: list[dict[str, Any]],
    synced: bool,
) -> str:
    lines = [
        "# RAGForge repository bootstrap", "",
        f"Task: {task_id or 'ad-hoc'}",
        f"Task spec: {task_path or 'none'}",
        f"Ownership query: {ownership_query}",
        f"Behavior query: {behavior_query}",
        f"Incremental sync: {'yes' if synced else 'no'}", "",
        "Use these paths first. Inspect the named symbol/range, not whole large files.",
        "If this packet is insufficient, run at most one refinement with concrete behavior/symbol terms.",
        "Do not substitute repo-wide rg/find inventory for a refinement.", "",
    ]
    for index, item in enumerate(results, 1):
        path = str(item.get("path") or "")
        start = int(item.get("start_line") or 1)
        end = int(item.get("end_line") or start)
        symbol = str(item.get("symbol") or "<module>")
        reasons = ",".join(str(x) for x in item.get("reasons") or [])
        excerpt = re.sub(r"\s+", " ", str(item.get("excerpt") or "")).strip()[:MAX_EXCERPT_CHARS]
        lines.append(f"{index}. `{path}:{start}-{end}` — `{symbol}` [{reasons}]")
        if excerpt:
            lines.append(f"   {excerpt}")
    return ("\n".join(lines).rstrip() + "\n")[:MAX_PACKET_CHARS]


def main() -> int:
    _stdout_utf8()
    parser = argparse.ArgumentParser(description="RAGForge source-oriented Repo Brain bootstrap")
    parser.add_argument("--task", help="Active task id, e.g. LLM-CTRL-01")
    parser.add_argument("--query", default="", help="Concrete goal/symbol/behavior terms")
    parser.add_argument("--top", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    task_id = args.task.upper() if args.task else None
    task_spec = _find_task_spec(task_id)
    spec_text = task_spec.read_text(encoding="utf-8", errors="replace") if task_spec else ""
    if not args.query and not spec_text:
        print("Provide --task with an existing task spec or --query.", file=sys.stderr)
        return 2

    ownership_query, behavior_query, anchors = build_brain_queries(args.query or spec_text, task_id, spec_text)
    query_terms = _keywords(TASK_ID_RE.sub(" ", f"{args.query} {_extract_task_summary(spec_text)}"))[:40]
    try:
        raw, synced = _brain_queries([ownership_query, behavior_query])
    except Exception as exc:
        print(f"Repo bootstrap failed: {exc}", file=sys.stderr)
        return 2

    task_rel = task_spec.relative_to(ROOT).as_posix() if task_spec else None
    selected = diversify_results(
        raw,
        task_path=task_rel,
        limit=max(1, min(args.top, 30)),
        anchors=anchors,
        query_terms=query_terms,
    )
    if not [item for item in selected if _is_source(item)]:
        print(
            "Repo bootstrap returned no implementation/test evidence. "
            "Refine once with concrete feature/symbol/endpoint/behavior terms.",
            file=sys.stderr,
        )
        return 2
    print(render_packet(task_id, task_rel, ownership_query, behavior_query, selected, synced), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
