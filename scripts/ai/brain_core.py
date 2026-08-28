#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from _brain_sources import classify_source, enumerate_sources
except ImportError:  # pragma: no cover - only for isolated tooling tests
    classify_source = None  # type: ignore[assignment]
    enumerate_sources = None  # type: ignore[assignment]

SCHEMA_VERSION = 1
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_CHUNK_LINES = 180
GENERIC_WINDOW = 120
GENERIC_OVERLAP = 20
PRIVATE_FILES = (
    "HANDOFF.md",
    "CHANGE_HISTORY.jsonl",
    "BUGS.json",
    "TECH_DEBT.json",
    "FAILED_APPROACHES.json",
)
TOKEN_RE = re.compile(r"[A-Za-z0-9_./:@+-]{2,}")
TASK_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+[A-Z0-9]*\b")
FASTAPI_RE = re.compile(
    r"(?P<router>[A-Za-z_][\w.]*)\.(?P<method>get|post|put|patch|delete|options|head|websocket)"
    r"\(\s*[\"'](?P<path>[^\"']+)"
)
JS_SYMBOL_RE = re.compile(
    r"(?:^|\n)\s*(?:export\s+(?:default\s+)?)?"
    r"(?:(?:async\s+)?function|class|const|let|var)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
JS_IMPORT_RE = re.compile(r"\bimport\b[\s\S]*?\bfrom\s+[\"']([^\"']+)[\"']")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    path: str
    kind: str
    symbol: str
    start_line: int
    end_line: int
    text: str
    source_class: str
    service: str
    is_private: int = 0


@dataclass(frozen=True)
class Edge:
    src_chunk: str
    src_symbol: str
    edge_kind: str
    dst_value: str
    path: str
    line: int


def _repo_source_class(path: str) -> str:
    if classify_source is not None:
        return str(classify_source(path))
    posix = path.replace("\\", "/")
    if posix in {
        "AGENTS.md",
        "CLAUDE.md",
        ".python-version",
        "docs/ai/RUNTIME_CONTRACT.md",
        "docs/ai/ENGINEERING_RULES.md",
        "docs/ai/TESTING.md",
        "docs/ai/TESTING_OPTIMIZED.md",
        "docs/ai/WORKFLOW.md",
    }:
        return "authoritative"
    if posix.startswith("docs/ai/tasks/"):
        return "task"
    if posix.startswith(("docs/ai/archive/", "docs/ai/tasks/archive/")):
        return "history"
    return "source"


def _service(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[0] == "backend":
        return parts[1]
    if parts and parts[0] == "frontend":
        return "frontend"
    if parts[:2] == ["docs", "ai"]:
        return "docs-ai"
    if parts[:2] == ["scripts", "ai"]:
        return "agent-tooling"
    if parts and parts[0] == ".agent-private":
        return "private-memory"
    return parts[0] if parts else "root"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _chunk_id(path: str, kind: str, symbol: str, start: int, end: int, text: str) -> str:
    raw = f"{path}\0{kind}\0{symbol}\0{start}\0{end}\0{_sha(text)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _bounded_text(lines: Sequence[str], start: int, end: int) -> str:
    start = max(1, start)
    end = min(len(lines), max(start, end))
    count = end - start + 1
    if count <= MAX_CHUNK_LINES:
        return "\n".join(lines[start - 1 : end])
    head = lines[start - 1 : start - 1 + 120]
    tail = lines[end - 40 : end]
    return "\n".join([*head, "# ... chunk truncated ...", *tail])


def _simple_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _simple_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _python_chunks(path: str, text: str, source_class: str, is_private: int) -> tuple[list[Chunk], list[Edge]]:
    lines = text.splitlines()
    chunks: list[Chunk] = []
    edges: list[Edge] = []
    service = _service(path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _generic_chunks(path, text, source_class, is_private)

    module_end = min(len(lines), 120)
    module_text = _bounded_text(lines, 1, module_end) if lines else ""
    module_id = _chunk_id(path, "module", "<module>", 1, module_end or 1, module_text)
    chunks.append(Chunk(module_id, path, "module", "<module>", 1, module_end or 1, module_text, source_class, service, is_private))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            else:
                modules = ["." * node.level + (node.module or "")]
            for module in modules:
                if module:
                    edges.append(Edge(module_id, "<module>", "imports", module, path, getattr(node, "lineno", 1)))

    stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            symbol = ".".join([*stack, node.name])
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            body = _bounded_text(lines, start, end)
            cid = _chunk_id(path, "class", symbol, start, end, body)
            chunks.append(Chunk(cid, path, "class", symbol, start, end, body, source_class, service, is_private))
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            symbol = ".".join([*stack, node.name])
            kind = "method" if stack else "function"
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            body = _bounded_text(lines, start, end)
            cid = _chunk_id(path, kind, symbol, start, end, body)
            chunks.append(Chunk(cid, path, kind, symbol, start, end, body, source_class, service, is_private))
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = _simple_name(child.func)
                    if name:
                        edges.append(Edge(cid, symbol, "calls", name, path, getattr(child, "lineno", start)))
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_FunctionDef = _visit_fn
        visit_AsyncFunctionDef = _visit_fn

    Visitor().visit(tree)

    for match in FASTAPI_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        owner = min(chunks, key=lambda c: abs(c.start_line - line)) if chunks else None
        src = owner.chunk_id if owner else module_id
        symbol = owner.symbol if owner else "<module>"
        route = f"{match.group('method').upper()} {match.group('path')}"
        edges.append(Edge(src, symbol, "route", route, path, line))

    return chunks, edges


def _js_chunks(path: str, text: str, source_class: str, is_private: int) -> tuple[list[Chunk], list[Edge]]:
    lines = text.splitlines()
    service = _service(path)
    matches = list(JS_SYMBOL_RE.finditer(text))
    chunks: list[Chunk] = []
    edges: list[Edge] = []
    module_end = min(len(lines), 100)
    module_text = _bounded_text(lines, 1, module_end) if lines else ""
    module_id = _chunk_id(path, "module", "<module>", 1, module_end or 1, module_text)
    chunks.append(Chunk(module_id, path, "module", "<module>", 1, module_end or 1, module_text, source_class, service, is_private))

    for i, match in enumerate(matches):
        name = match.group(1)
        start = text.count("\n", 0, match.start()) + 1
        next_start = text.count("\n", 0, matches[i + 1].start()) + 1 if i + 1 < len(matches) else len(lines) + 1
        end = min(len(lines), max(start, next_start - 1), start + MAX_CHUNK_LINES - 1)
        body = _bounded_text(lines, start, end)
        kind = "component" if name[:1].isupper() else ("hook" if name.startswith("use") else "symbol")
        cid = _chunk_id(path, kind, name, start, end, body)
        chunks.append(Chunk(cid, path, kind, name, start, end, body, source_class, service, is_private))

    for match in JS_IMPORT_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        edges.append(Edge(module_id, "<module>", "imports", match.group(1), path, line))
    return chunks, edges


def _markdown_chunks(path: str, text: str, source_class: str, is_private: int) -> tuple[list[Chunk], list[Edge]]:
    lines = text.splitlines()
    service = _service(path)
    headings: list[tuple[int, str]] = []
    for i, line in enumerate(lines, 1):
        if line.startswith("#"):
            title = line.lstrip("#").strip() or "section"
            headings.append((i, title))
    if not headings:
        return _generic_chunks(path, text, source_class, is_private)
    chunks: list[Chunk] = []
    for idx, (start, title) in enumerate(headings):
        end = (headings[idx + 1][0] - 1) if idx + 1 < len(headings) else len(lines)
        body = _bounded_text(lines, start, end)
        cid = _chunk_id(path, "section", title, start, end, body)
        chunks.append(Chunk(cid, path, "section", title, start, end, body, source_class, service, is_private))
    return chunks, []


def _generic_chunks(path: str, text: str, source_class: str, is_private: int) -> tuple[list[Chunk], list[Edge]]:
    lines = text.splitlines()
    service = _service(path)
    if not lines:
        lines = [""]
    chunks: list[Chunk] = []
    step = max(1, GENERIC_WINDOW - GENERIC_OVERLAP)
    for start0 in range(0, len(lines), step):
        start = start0 + 1
        end = min(len(lines), start0 + GENERIC_WINDOW)
        body = "\n".join(lines[start0:end])
        symbol = f"lines-{start}-{end}"
        cid = _chunk_id(path, "text", symbol, start, end, body)
        chunks.append(Chunk(cid, path, "text", symbol, start, end, body, source_class, service, is_private))
        if end >= len(lines):
            break
    return chunks, []


def build_chunks(path: str, text: str, source_class: str, is_private: int = 0) -> tuple[list[Chunk], list[Edge]]:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return _python_chunks(path, text, source_class, is_private)
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return _js_chunks(path, text, source_class, is_private)
    if suffix == ".md":
        return _markdown_chunks(path, text, source_class, is_private)
    return _generic_chunks(path, text, source_class, is_private)


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def _enumerate(root: Path) -> list[str]:
    if enumerate_sources is not None:
        return list(enumerate_sources(root))
    raw = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    paths = [p for p in raw.split("\0") if p] if raw else []
    allowed = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml", ".toml", ".md"}
    out = []
    for rel in paths:
        p = root / rel
        if p.is_file() and (p.suffix.lower() in allowed or p.name == ".python-version"):
            out.append(rel.replace("\\", "/"))
    return sorted(set(out))


class Brain:
    def __init__(self, root: Path, db_path: Path | None = None):
        self.root = root.resolve()
        self.db_path = db_path or (self.root / ".agent-private" / "brain" / "brain.sqlite3")

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                source_class TEXT NOT NULL,
                service TEXT NOT NULL,
                is_private INTEGER NOT NULL DEFAULT 0,
                indexed_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                kind TEXT NOT NULL,
                symbol TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                text TEXT NOT NULL,
                source_class TEXT NOT NULL,
                service TEXT NOT NULL,
                is_private INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
            CREATE INDEX IF NOT EXISTS idx_chunks_symbol ON chunks(symbol);
            CREATE INDEX IF NOT EXISTS idx_chunks_service ON chunks(service);
            CREATE INDEX IF NOT EXISTS idx_chunks_private ON chunks(is_private);
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                src_chunk TEXT NOT NULL,
                src_symbol TEXT NOT NULL,
                edge_kind TEXT NOT NULL,
                dst_value TEXT NOT NULL,
                path TEXT NOT NULL,
                line INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_chunk);
            CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_value);
            CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(edge_kind);
            """
        )
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
            "chunk_id UNINDEXED, path, symbol, kind, text, source_class UNINDEXED, service UNINDEXED, is_private UNINDEXED)"
        )
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.commit()

    def _source_rows(self) -> list[tuple[str, Path, str, int]]:
        rows: list[tuple[str, Path, str, int]] = []
        for rel in _enumerate(self.root):
            path = self.root / rel
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            rows.append((rel, path, _repo_source_class(rel), 0))
        private_root = self.root / ".agent-private"
        for name in PRIVATE_FILES:
            path = private_root / name
            if path.is_file():
                try:
                    if path.stat().st_size <= MAX_FILE_BYTES:
                        rows.append((f".agent-private/{name}", path, "history", 1))
                except OSError:
                    pass
        return rows

    def sync(self, full: bool = False) -> dict[str, int | str]:
        started = time.perf_counter()
        with closing(self.connect()) as conn, conn:
            self.ensure_schema(conn)
            existing = {
                str(row["path"]): (int(row["size"]), int(row["mtime_ns"]), str(row["sha256"]))
                for row in conn.execute("SELECT path,size,mtime_ns,sha256 FROM files")
            }
            source_rows = self._source_rows()
            current_paths = {rel for rel, _, _, _ in source_rows}
            deleted = sorted(set(existing) - current_paths)
            for rel in deleted:
                self._delete_path(conn, rel)

            changed = 0
            unchanged = 0
            chunk_count = 0
            edge_count = 0
            for rel, path, source_class, is_private in source_rows:
                try:
                    stat = path.stat()
                except OSError:
                    continue
                prev = existing.get(rel)
                if not full and prev and prev[0] == stat.st_size and prev[1] == stat.st_mtime_ns:
                    unchanged += 1
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                digest = _sha(text)
                if not full and prev and prev[2] == digest:
                    conn.execute("UPDATE files SET size=?, mtime_ns=? WHERE path=?", (stat.st_size, stat.st_mtime_ns, rel))
                    unchanged += 1
                    continue
                chunks, edges = build_chunks(rel, text, source_class, is_private)
                self._delete_path(conn, rel)
                conn.execute(
                    "INSERT INTO files(path,size,mtime_ns,sha256,source_class,service,is_private,indexed_at) VALUES(?,?,?,?,?,?,?,?)",
                    (rel, stat.st_size, stat.st_mtime_ns, digest, source_class, _service(rel), is_private, time.time()),
                )
                conn.executemany(
                    "INSERT INTO chunks(chunk_id,path,kind,symbol,start_line,end_line,text,source_class,service,is_private) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    [(c.chunk_id, c.path, c.kind, c.symbol, c.start_line, c.end_line, c.text, c.source_class, c.service, c.is_private) for c in chunks],
                )
                conn.executemany(
                    "INSERT INTO chunks_fts(chunk_id,path,symbol,kind,text,source_class,service,is_private) VALUES(?,?,?,?,?,?,?,?)",
                    [(c.chunk_id, c.path, c.symbol, c.kind, c.text, c.source_class, c.service, c.is_private) for c in chunks],
                )
                conn.executemany(
                    "INSERT INTO edges(src_chunk,src_symbol,edge_kind,dst_value,path,line) VALUES(?,?,?,?,?,?)",
                    [(e.src_chunk, e.src_symbol, e.edge_kind, e.dst_value, e.path, e.line) for e in edges],
                )
                changed += 1
                chunk_count += len(chunks)
                edge_count += len(edges)

            head = _git(self.root, "rev-parse", "HEAD") or "unknown"
            dirty = "1" if _git(self.root, "status", "--porcelain") else "0"
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('git_head',?)", (head,))
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('dirty_at_sync',?)", (dirty,))
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('synced_at',?)", (str(time.time()),))
            conn.commit()
            total_files = int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0])
            total_chunks = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
            total_edges = int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0])
        return {
            "changed_files": changed,
            "unchanged_files": unchanged,
            "deleted_files": len(deleted),
            "new_chunks": chunk_count,
            "new_edges": edge_count,
            "total_files": total_files,
            "total_chunks": total_chunks,
            "total_edges": total_edges,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "head": head,
        }

    def _delete_path(self, conn: sqlite3.Connection, rel: str) -> None:
        conn.execute("DELETE FROM chunks_fts WHERE path=?", (rel,))
        conn.execute("DELETE FROM edges WHERE path=?", (rel,))
        conn.execute("DELETE FROM chunks WHERE path=?", (rel,))
        conn.execute("DELETE FROM files WHERE path=?", (rel,))

    def stale_paths(self, limit: int = 1000) -> list[str]:
        if not self.db_path.exists():
            return ["<brain database missing>"]
        with closing(self.connect()) as conn, conn:
            self.ensure_schema(conn)
            indexed = {str(r["path"]): (int(r["size"]), int(r["mtime_ns"])) for r in conn.execute("SELECT path,size,mtime_ns FROM files")}
        rows = self._source_rows()
        current = {rel: path for rel, path, _, _ in rows}
        stale: list[str] = []
        for rel, path in current.items():
            prev = indexed.get(rel)
            try:
                st = path.stat()
            except OSError:
                continue
            if prev is None or prev != (st.st_size, st.st_mtime_ns):
                stale.append(rel)
                if len(stale) >= limit:
                    return stale
        for rel in indexed:
            if rel not in current:
                stale.append(rel)
                if len(stale) >= limit:
                    break
        return stale

    def status(self) -> dict[str, object]:
        if not self.db_path.exists():
            return {"database": str(self.db_path), "exists": False, "stale": True, "stale_paths": ["<missing>"]}
        with closing(self.connect()) as conn, conn:
            self.ensure_schema(conn)
            meta = {str(r["key"]): str(r["value"]) for r in conn.execute("SELECT key,value FROM meta")}
            counts = {
                "files": int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]),
                "chunks": int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]),
                "edges": int(conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]),
            }
        stale = self.stale_paths(limit=20)
        return {
            "database": str(self.db_path),
            "exists": True,
            "schema_version": meta.get("schema_version"),
            "indexed_head": meta.get("git_head"),
            "current_head": _git(self.root, "rev-parse", "HEAD") or "unknown",
            **counts,
            "stale": bool(stale),
            "stale_paths": stale,
        }

    def doctor(self) -> tuple[bool, dict[str, object]]:
        details: dict[str, object] = {}
        try:
            with closing(self.connect()) as conn, conn:
                self.ensure_schema(conn)
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __brain_fts_probe USING fts5(x)")
                conn.execute("DROP TABLE IF EXISTS __brain_fts_probe")
                integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
                details["sqlite_integrity"] = integrity
                details["fts5"] = True
        except Exception as exc:
            details["error"] = str(exc)
            return False, details
        status = self.status()
        details.update(status)
        ok = details.get("sqlite_integrity") == "ok" and not bool(status.get("stale"))
        return ok, details

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = []
        seen = set()
        for token in TOKEN_RE.findall(query):
            low = token.lower()
            if low not in seen:
                seen.add(low)
                safe = token.replace('"', '""')
                tokens.append(f'"{safe}"')
        return " OR ".join(tokens[:20])

    def query(self, query: str, top: int = 20, public_only: bool = False) -> list[dict[str, object]]:
        if not self.db_path.exists():
            self.sync()
        top = max(1, min(int(top), 100))
        with closing(self.connect()) as conn, conn:
            self.ensure_schema(conn)
            candidates: dict[str, dict[str, object]] = {}
            exact_rows: list[sqlite3.Row] = []
            q = query.strip()
            task_ids = set(TASK_ID_RE.findall(q.upper()))
            tokens = [t.lower() for t in TOKEN_RE.findall(q)][:20]

            privacy_sql = " AND is_private=0" if public_only else ""
            if q:
                exact_rows.extend(
                    conn.execute(
                        f"SELECT * FROM chunks WHERE (lower(symbol)=lower(?) OR lower(path)=lower(?) OR lower(symbol) LIKE lower(?) OR lower(path) LIKE lower(?)){privacy_sql} LIMIT 120",
                        (q, q, f"%{q}%", f"%{q}%"),
                    ).fetchall()
                )
            for token in tokens[:6]:
                exact_rows.extend(
                    conn.execute(
                        f"SELECT * FROM chunks WHERE (lower(symbol)=? OR lower(symbol) LIKE ? OR lower(path) LIKE ?){privacy_sql} LIMIT 80",
                        (token, f"%{token}%", f"%{token}%"),
                    ).fetchall()
                )

            seen_exact: set[str] = set()
            rank = 0
            for row in exact_rows:
                cid = str(row["chunk_id"])
                if cid in seen_exact:
                    continue
                seen_exact.add(cid)
                rank += 1
                item = self._row_item(row)
                boost = self._authority_boost(str(row["source_class"]), str(row["path"]), task_ids)
                score = 2.0 / (50 + rank) + boost
                self._merge_candidate(candidates, item, score, "exact")

            fts = self._fts_query(q)
            if fts:
                fts_rows = conn.execute(
                    "SELECT c.*, bm25(chunks_fts, 0.0, 1.2, 2.0, 0.5, 1.0) AS bm "
                    "FROM chunks_fts JOIN chunks c ON c.chunk_id=chunks_fts.chunk_id "
                    "WHERE chunks_fts MATCH ? " + ("AND c.is_private=0 " if public_only else "") + "ORDER BY bm LIMIT ?",
                    (fts, max(top * 6, 60)),
                ).fetchall()
                for rank, row in enumerate(fts_rows, 1):
                    item = self._row_item(row)
                    boost = self._authority_boost(str(row["source_class"]), str(row["path"]), task_ids)
                    score = 3.0 / (50 + rank) + boost
                    self._merge_candidate(candidates, item, score, "bm25")

            initial = sorted(candidates.values(), key=lambda x: (-float(x["score"]), str(x["path"])))[: max(top * 2, 20)]
            self._expand_graph(conn, candidates, initial, public_only)

        ranked = sorted(candidates.values(), key=lambda x: (-float(x["score"]), str(x["path"]), int(x["start_line"])))
        deduped: list[dict[str, object]] = []
        seen_key: set[tuple[str, str, int]] = set()
        for item in ranked:
            key = (str(item["path"]), str(item["symbol"]), int(item["start_line"]))
            if key in seen_key:
                continue
            seen_key.add(key)
            deduped.append(item)
            if len(deduped) >= top:
                break
        return deduped

    @staticmethod
    def _authority_boost(source_class: str, path: str, task_ids: set[str]) -> float:
        base = {"authoritative": 0.035, "source": 0.010, "task": 0.012, "history": -0.035}.get(source_class, 0.0)
        if task_ids and source_class == "task" and any(tid in path.upper() for tid in task_ids):
            base += 0.110
        return base

    @staticmethod
    def _row_item(row: sqlite3.Row) -> dict[str, object]:
        text = str(row["text"])
        excerpt = re.sub(r"\s+", " ", text).strip()[:700]
        return {
            "chunk_id": str(row["chunk_id"]),
            "path": str(row["path"]),
            "kind": str(row["kind"]),
            "symbol": str(row["symbol"]),
            "start_line": int(row["start_line"]),
            "end_line": int(row["end_line"]),
            "source_class": str(row["source_class"]),
            "service": str(row["service"]),
            "is_private": bool(row["is_private"]),
            "excerpt": excerpt,
            "score": 0.0,
            "reasons": [],
        }

    @staticmethod
    def _merge_candidate(candidates: dict[str, dict[str, object]], item: dict[str, object], score: float, reason: str) -> None:
        cid = str(item["chunk_id"])
        existing = candidates.get(cid)
        if existing is None:
            item["score"] = score
            item["reasons"] = [reason]
            candidates[cid] = item
            return
        existing["score"] = float(existing["score"]) + score
        reasons = list(existing.get("reasons", []))
        if reason not in reasons:
            reasons.append(reason)
        existing["reasons"] = reasons

    def _expand_graph(self, conn: sqlite3.Connection, candidates: dict[str, dict[str, object]], seeds: Sequence[dict[str, object]], public_only: bool) -> None:
        seed_ids = [str(s["chunk_id"]) for s in seeds[:12]]
        if not seed_ids:
            return
        placeholders = ",".join("?" for _ in seed_ids)
        edges = conn.execute(
            f"SELECT src_chunk,src_symbol,edge_kind,dst_value FROM edges WHERE src_chunk IN ({placeholders}) LIMIT 250",
            seed_ids,
        ).fetchall()
        dst_names = []
        for edge in edges:
            value = str(edge["dst_value"])
            if str(edge["edge_kind"]) == "calls":
                dst_names.append(value.rsplit(".", 1)[-1])
        for name in sorted(set(dst_names))[:40]:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE (symbol=? OR symbol LIKE ?) " + ("AND is_private=0 " if public_only else "") + "LIMIT 8",
                (name, f"%.{name}"),
            ).fetchall()
            for row in rows:
                item = self._row_item(row)
                self._merge_candidate(candidates, item, 0.018, "graph:called-symbol")

        symbols = [str(s["symbol"]).rsplit(".", 1)[-1] for s in seeds if str(s["symbol"]) not in {"", "<module>"}]
        for symbol in sorted(set(symbols))[:30]:
            callers = conn.execute(
                "SELECT DISTINCT c.* FROM edges e JOIN chunks c ON c.chunk_id=e.src_chunk "
                "WHERE e.edge_kind='calls' AND (e.dst_value=? OR e.dst_value LIKE ?) "
                + ("AND c.is_private=0 " if public_only else "") + "LIMIT 8",
                (symbol, f"%.{symbol}"),
            ).fetchall()
            for row in callers:
                item = self._row_item(row)
                self._merge_candidate(candidates, item, 0.014, "graph:caller")

    def context(self, query: str, top: int = 12, budget_chars: int = 12000, public_only: bool = False) -> str:
        results = self.query(query, top=top, public_only=public_only)
        remaining = max(1000, budget_chars)
        blocks: list[str] = []
        for item in results:
            path = self.root / str(item["path"])
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            start = max(1, int(item["start_line"]))
            end = min(len(lines), int(item["end_line"]), start + 120)
            body = "\n".join(lines[start - 1 : end])
            header = f"### {item['path']}:{start}-{end} — {item['symbol']} [{','.join(item['reasons'])}]\n"
            block = header + body + "\n"
            if len(block) > remaining:
                if remaining > len(header) + 300:
                    blocks.append(header + body[: remaining - len(header) - 20] + "\n…\n")
                break
            blocks.append(block)
            remaining -= len(block)
            if remaining < 500:
                break
        return "\n".join(blocks)


def json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
