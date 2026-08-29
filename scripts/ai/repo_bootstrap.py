#!/usr/bin/env python3
"""RAGForge source-oriented repository bootstrap.

Agent-neutral wrapper around Repo Brain v4.

Design goals:
- Keep Repo Brain v4 core/schema untouched.
- Never use the literal task id in broad retrieval after the task spec is known.
- Query each Primary scope item separately instead of one keyword soup query.
- Give explicit scoped paths deterministic priority.
- Cover distinct scope owners before filling remaining Top-K slots.
- Prefer implementation and tests over generic infrastructure matches.
- Emit JSON for machine verification and ASCII-only text for Windows terminals.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

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
MAX_SCOPE_QUERIES = 6

STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "only", "when",
    "where", "what", "should", "must", "task", "goal", "phase", "depends", "required",
    "current", "existing", "using", "used", "does", "not", "without", "after", "before",
    "then", "once", "full", "make", "keep", "clear", "real", "data", "show", "more",
    "less", "each", "every", "while", "acceptance", "criteria", "branch", "scope",
    "stop", "start", "replace", "default", "example", "implementation", "behavior",
    "behaviour", "support", "supported", "component", "components", "production",
    "files", "file", "code", "unless", "remove", "ownership", "potential",
}

DOMAIN_TERMS = {
    "frontend", "backend", "rag", "chat", "eval", "metrics", "memory", "gateway",
    "embedding", "vector", "document", "documents", "pipeline", "ingestion", "reindex",
    "rerun", "delete", "upload", "search", "filter", "sort", "table", "drawer", "bulk",
    "status", "review", "activity", "service", "router", "context", "retrieval", "runtime",
    "agent", "provider", "providers", "adapter", "adapters", "prompt", "registry", "schema",
    "typed", "control", "plane", "vllm", "model", "summary", "curation", "title",
    "execution", "telemetry", "decode", "validate", "invoke", "render", "plan", "rpc",
    "langchain", "dockerfile", "requirements", "tests", "test", "caller", "callers",
    "config", "configuration", "structured", "output", "finish", "reason", "error",
}

GENERIC_PATH_PENALTIES = (
    "/core/errors.py",
    "/core/exception_handlers.py",
    "/cache/",
    "/rest/controllers.py",
)

CALLER_SIGNAL_TERMS = (
    "llm", "rpc", "request", "title", "summary", "curation", "chat_exit",
    "completion", "model", "generate", "typed",
)


@dataclass(frozen=True)
class QueryPlanItem:
    label: str
    query: str
    weight: float


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


def _scope_bullets(spec_text: str) -> list[str]:
    scope = _section(spec_text, "Primary scope")
    bullets: list[str] = []
    for line in scope.splitlines():
        stripped = re.sub(r"^[\s*+-]+", "", line).strip()
        if stripped:
            bullets.append(stripped)
    return bullets


def _explicit_scope_paths(spec_text: str) -> list[str]:
    paths: list[str] = []
    for raw in CODE_SPAN_RE.findall(_section(spec_text, "Primary scope")):
        candidate = raw.strip().replace("\\", "/")
        if not candidate or candidate.startswith(("http://", "https://")):
            continue
        target = (ROOT / candidate).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            continue
        if target.is_file() and candidate not in paths:
            paths.append(candidate)
    return paths


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


def _informative_terms(text: str) -> list[str]:
    # In prose, slash usually means alternatives (registry/config, requirements/Dockerfile),
    # not a filesystem path. Exact scoped paths bypass this tokenizer in the query plan.
    prose = re.sub(r"(?<=[A-Za-z])/(?=[A-Za-z])", " ", TASK_ID_RE.sub(" ", text))
    terms: list[str] = []
    for token in _keywords(prose):
        if token not in terms:
            terms.append(token)
    return terms


def _scope_anchors(spec_text: str) -> list[str]:
    anchors: list[str] = []
    for path in _explicit_scope_paths(spec_text):
        for value in (path, Path(path).name, Path(path).stem):
            low = _normalize_keyword(value)
            if low and low not in anchors:
                anchors.append(low)
    for bullet in _scope_bullets(spec_text):
        for token in _informative_terms(bullet):
            if token not in anchors:
                anchors.append(token)
    return anchors[:32]


def _required_behavior_lines(spec_text: str) -> list[str]:
    behavior = _section(spec_text, "Required behavior")
    lines: list[str] = []
    for line in behavior.splitlines():
        stripped = re.sub(r"^[\s*+-]+", "", line).strip()
        if stripped:
            lines.append(stripped)
    return lines


def build_query_plan(raw_query: str, task_id: str | None, spec_text: str = "") -> list[QueryPlanItem]:
    """Build small focused Brain queries instead of one broad keyword soup."""
    plan: list[QueryPlanItem] = []
    seen: set[str] = set()

    def add(label: str, query: str, weight: float, *, preserve: bool = False) -> None:
        query = query.strip() if preserve else " ".join(_informative_terms(query)[:16]).strip()
        if not query or query in seen:
            return
        seen.add(query)
        plan.append(QueryPlanItem(label=label, query=query, weight=weight))

    # Exact task-owned paths get dedicated queries. This makes their presence
    # deterministic instead of hoping they survive a broad BM25 query.
    for path in _explicit_scope_paths(spec_text):
        add(f"explicit:{path}", path, 4.0, preserve=True)

    # Each conceptual scope bullet gets its own focused lookup. The Brain call is
    # cheap/local and saves the agent from doing broad rg/find discovery later.
    for index, bullet in enumerate(_scope_bullets(spec_text)[:MAX_SCOPE_QUERIES], 1):
        add(f"scope:{index}", bullet, 2.2)

    # User goal and required behavior complement ownership retrieval.
    add("goal", TASK_ID_RE.sub(" ", raw_query or ""), 1.6)
    behavior_lines = _required_behavior_lines(spec_text)
    if behavior_lines:
        add("behavior", " ".join(behavior_lines[:4]), 1.5)

    if not plan:
        add("fallback", "repository source ownership tests", 1.0)
    return plan


def build_brain_queries(raw_query: str, task_id: str | None, spec_text: str = "") -> tuple[str, str, list[str]]:
    """Compatibility view for earlier callers/tests."""
    plan = build_query_plan(raw_query, task_id, spec_text)
    first = plan[0].query if plan else "repository source ownership"
    second = plan[1].query if len(plan) > 1 else first
    return first, second, _scope_anchors(spec_text)


def build_brain_query(raw_query: str, task_id: str | None, spec_text: str = "") -> str:
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


def _brain_queries(plan: Sequence[QueryPlanItem]) -> tuple[list[dict[str, Any]], bool]:
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
    for item_plan in plan:
        for rank, raw in enumerate(brain.query(item_plan.query, top=60), 1):
            item = dict(raw)
            cid = str(item.get("chunk_id") or f"{item.get('path')}:{item.get('start_line')}:{item.get('symbol')}")
            contribution = item_plan.weight / (6.0 + rank)
            existing = merged.get(cid)
            if existing is None:
                item["bootstrap_retrieval_score"] = contribution
                item["bootstrap_query_labels"] = [item_plan.label]
                merged[cid] = item
            else:
                existing["bootstrap_retrieval_score"] = float(existing.get("bootstrap_retrieval_score", 0.0)) + contribution
                labels = list(existing.get("bootstrap_query_labels", []))
                if item_plan.label not in labels:
                    labels.append(item_plan.label)
                existing["bootstrap_query_labels"] = labels
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


def _candidate_text(item: dict[str, Any]) -> tuple[str, str, str, str]:
    path = str(item.get("path") or "").replace("\\", "/").lower()
    symbol = str(item.get("symbol") or "").lower()
    excerpt = str(item.get("excerpt") or "").lower()
    combined = f"{path} {symbol} {excerpt}"
    return path, symbol, excerpt, combined


def _token_overlap_count(text: str, terms: Iterable[str]) -> int:
    return sum(1 for term in terms if term and term.lower() in text)


def _scope_match_score(item: dict[str, Any], bullet: str) -> float:
    path, symbol, excerpt, combined = _candidate_text(item)
    terms = _informative_terms(bullet)
    if not terms:
        return 0.0

    score = 0.0
    for term in terms:
        if term in path:
            score += 4.0
        if term in symbol:
            score += 3.0
        if term in excerpt:
            score += 0.8

    low = bullet.lower()
    if "memory" in low and ("caller" in low or "llm" in low):
        if not path.startswith("backend/memory/"):
            return 0.0
        signal_hits = _token_overlap_count(combined, CALLER_SIGNAL_TERMS)
        if signal_hits < 2:
            return 0.0
        score += 6.0 + signal_hits
        if "/services/" in path or "/agent/" in path:
            score += 2.0

    if "provider" in low and ("adapter" in low or "providers" in low):
        if "/llm/implementations/" in path or path.endswith("/llm/factories.py"):
            score += 7.0

    if "prompt" in low and "registry" in low:
        if "prompt_registry" in path or "promptregistry" in symbol.replace("_", ""):
            score += 10.0

    if "tests" in low or low.strip() == "tests":
        if _is_test_path(path):
            score += 8.0
        else:
            score -= 3.0

    return score


def _rerank_score(
    item: dict[str, Any],
    *,
    explicit_paths: list[str],
    scope_bullets: list[str],
    query_terms: list[str],
) -> float:
    path, symbol, excerpt, combined = _candidate_text(item)
    score = float(item.get("bootstrap_retrieval_score", 0.0)) * 10.0

    for explicit in explicit_paths:
        if path == explicit.lower():
            score += 100.0
        elif Path(explicit).stem.lower() in path or Path(explicit).stem.lower() in symbol:
            score += 12.0

    scope_scores = [_scope_match_score(item, bullet) for bullet in scope_bullets]
    if scope_scores:
        score += max(scope_scores) * 2.5
        score += sum(sorted(scope_scores, reverse=True)[1:3]) * 0.35

    for term in query_terms:
        if term in path:
            score += 1.2
        if term in symbol:
            score += 0.9
        if term in excerpt:
            score += 0.12

    if _is_test_path(path):
        score += 0.25
    if "/services/" in path or "/llm/" in path or "/schemas/" in path:
        score += 0.25
    if any(fragment in path for fragment in GENERIC_PATH_PENALTIES):
        explicit = path in {p.lower() for p in explicit_paths}
        meaningful_scope = max(scope_scores or [0.0]) >= 6.0
        if not explicit and not meaningful_scope:
            score -= 6.0
    return score


def diversify_results(
    results: Iterable[dict[str, Any]],
    *,
    task_path: str | None = None,
    limit: int = DEFAULT_LIMIT,
    explicit_paths: list[str] | None = None,
    scope_bullets: list[str] | None = None,
    query_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    explicit_paths = explicit_paths or []
    scope_bullets = scope_bullets or []
    query_terms = query_terms or []
    ranked = sorted(
        list(results),
        key=lambda item: (
            -_rerank_score(
                item,
                explicit_paths=explicit_paths,
                scope_bullets=scope_bullets,
                query_terms=query_terms,
            ),
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
        return _is_source(item)

    def add(item: dict[str, Any]) -> bool:
        if len(selected) >= limit or not usable(item):
            return False
        path = str(item.get("path") or "").replace("\\", "/")
        key = str(item.get("chunk_id") or f"{path}:{item.get('start_line')}:{item.get('symbol')}")
        if key in seen or path_counts[path] >= MAX_PRIMARY_RESULTS_PER_PATH:
            return False
        selected.append(item)
        seen.add(key)
        path_counts[path] += 1
        return True

    # 1) Explicit path owners are non-negotiable when the task names them.
    for explicit in explicit_paths:
        exact = [item for item in ranked if str(item.get("path") or "").replace("\\", "/") == explicit]
        if exact:
            add(exact[0])

    # 2) Reserve one strong owner for each conceptual Primary scope bullet.
    for bullet in scope_bullets:
        if len(selected) >= limit:
            break
        candidates = [item for item in ranked if usable(item)]
        if not candidates:
            continue
        best = max(candidates, key=lambda item: _scope_match_score(item, bullet))
        best_score = _scope_match_score(best, bullet)
        terms = _informative_terms(bullet)
        threshold = 5.0 if len(terms) >= 2 else 2.5
        if best_score >= threshold:
            add(best)

    # 3) Ensure at least one test is visible when the Brain found one.
    for item in ranked:
        if len(selected) >= limit:
            break
        if usable(item) and _is_test_path(str(item.get("path") or "")):
            add(item)
            break

    # 4) Fill remaining slots by reranked relevance, still capped per path.
    for item in ranked:
        if len(selected) >= limit:
            break
        add(item)

    return selected


def _result_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(item.get("path") or ""),
        "start_line": int(item.get("start_line") or 1),
        "end_line": int(item.get("end_line") or int(item.get("start_line") or 1)),
        "symbol": str(item.get("symbol") or "<module>"),
        "source_class": str(item.get("source_class") or ""),
        "reasons": [str(x) for x in item.get("reasons") or []],
        "excerpt": re.sub(r"\s+", " ", str(item.get("excerpt") or "")).strip()[:MAX_EXCERPT_CHARS],
    }


def render_packet(payload: dict[str, Any]) -> str:
    lines = [
        "# RAGForge repository bootstrap",
        "",
        f"Task: {payload['task_id'] or 'ad-hoc'}",
        f"Task spec: {payload['task_path'] or 'none'}",
        f"Incremental sync: {'yes' if payload['synced'] else 'no'}",
        "Query plan:",
    ]
    for item in payload["query_plan"]:
        lines.append(f"- {item['label']}: {item['query']}")
    lines.extend([
        "",
        "Use these paths first. Inspect the named symbol/range, not whole large files.",
        "If this packet is insufficient, run at most one refinement with concrete behavior/symbol terms.",
        "Do not substitute repo-wide rg/find inventory for a refinement.",
        "",
    ])
    for index, item in enumerate(payload["results"], 1):
        reasons = ",".join(item["reasons"])
        lines.append(
            f"{index}. `{item['path']}:{item['start_line']}-{item['end_line']}` -- "
            f"`{item['symbol']}` [{reasons}]"
        )
        if item["excerpt"]:
            lines.append(f"   {item['excerpt']}")
    return ("\n".join(lines).rstrip() + "\n")[:MAX_PACKET_CHARS]


def build_payload(task_id: str | None, raw_query: str, top: int) -> dict[str, Any]:
    task_spec = _find_task_spec(task_id)
    spec_text = task_spec.read_text(encoding="utf-8", errors="replace") if task_spec else ""
    if not raw_query and not spec_text:
        raise ValueError("Provide --task with an existing task spec or --query.")

    plan = build_query_plan(raw_query or spec_text, task_id, spec_text)
    raw, synced = _brain_queries(plan)
    task_rel = task_spec.relative_to(ROOT).as_posix() if task_spec else None
    explicit_paths = _explicit_scope_paths(spec_text)
    scope_bullets = _scope_bullets(spec_text)
    query_terms = _informative_terms(f"{raw_query} {_extract_task_summary(spec_text)}")[:48]
    selected = diversify_results(
        raw,
        task_path=task_rel,
        limit=max(1, min(top, 30)),
        explicit_paths=explicit_paths,
        scope_bullets=scope_bullets,
        query_terms=query_terms,
    )
    if not selected:
        raise RuntimeError(
            "Repo bootstrap returned no implementation/test evidence. "
            "Refine once with concrete feature/symbol/endpoint/behavior terms."
        )

    return {
        "version": "1.2",
        "task_id": task_id,
        "task_path": task_rel,
        "synced": synced,
        "query_plan": [
            {"label": item.label, "query": item.query, "weight": item.weight}
            for item in plan
        ],
        "explicit_scope_paths": explicit_paths,
        "scope_bullets": scope_bullets,
        "results": [_result_payload(item) for item in selected],
    }


def main() -> int:
    _stdout_utf8()
    parser = argparse.ArgumentParser(description="RAGForge source-oriented Repo Brain bootstrap")
    parser.add_argument("--task", help="Active task id, e.g. LLM-CTRL-01")
    parser.add_argument("--query", default="", help="Concrete goal/symbol/behavior terms")
    parser.add_argument("--top", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    task_id = args.task.upper() if args.task else None
    try:
        payload = build_payload(task_id, args.query, args.top)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True))
        else:
            print(f"Repo bootstrap failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"ok": True, **payload}, ensure_ascii=True, indent=2))
    else:
        print(render_packet(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
