#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "ai" / "generated"

SKIP_DIRS = {
    ".git", ".next", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".venv", "venv", "coverage", "dist", "build", "logs",
    "qdrant_storage", "uploads", ".agent-private",
}
TEXT_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml", ".toml", ".md"}
FRONTEND_EXTS = {".js", ".jsx", ".ts", ".tsx"}
MAX_FILE_BYTES = 2 * 1024 * 1024

FASTAPI = re.compile(r"(?P<router>[A-Za-z_][\w\.]*)\.(?P<method>get|post|put|patch|delete|options|head|websocket)\(\s*[\"'](?P<path>[^\"']+)")
JS_EXPORT = re.compile(r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)")
JS_FUNC = re.compile(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")
JS_COMP = re.compile(r"\b(?:export\s+)?const\s+([A-Z][A-Za-z0-9_$]*)\s*=\s*(?:memo\()?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")
JS_HOOK = re.compile(r"\b(?:export\s+)?(?:const\s+)?(use[A-Z][A-Za-z0-9_$]*)\b")
JS_IMPORT = re.compile(r"\bimport\b[\s\S]*?\bfrom\s+[\"']([^\"']+)[\"']")
ENV_PY = re.compile(r"(?:os\.getenv|os\.environ\.get)\(\s*[\"']([A-Z0-9_]+)[\"']")
ENV_JS = re.compile(r"process\.env\.([A-Z0-9_]+)")
URL = re.compile(r"[\"'](/v\d+/[^\"']*)[\"']")

def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()

def iter_files() -> Iterable[Path]:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        if "docs/ai/generated" in path.as_posix():
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def py_index(path: Path, text: str):
    symbols, imports, routes, configs = [], [], [], sorted(set(ENV_PY.findall(text)))
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return symbols, imports, routes, configs

    stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            symbols.append({"name": node.name, "kind": "class", "path": rel(path), "line": node.lineno, "qualname": ".".join(stack + [node.name])})
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            symbols.append({"name": node.name, "kind": "method" if stack else "function", "path": rel(path), "line": node.lineno, "qualname": ".".join(stack + [node.name])})
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_FunctionDef = _function
        visit_AsyncFunctionDef = _function

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                imports.append({"path": rel(path), "module": alias.name, "line": node.lineno})

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            imports.append({"path": rel(path), "module": "." * node.level + (node.module or ""), "line": node.lineno})

    Visitor().visit(tree)
    for match in FASTAPI.finditer(text):
        routes.append(f"{match.group('method').upper()} {match.group('path')}")
    return symbols, imports, sorted(set(routes)), configs

def js_index(path: Path, text: str):
    symbols = []
    names = set(JS_EXPORT.findall(text)) | set(JS_FUNC.findall(text)) | set(JS_COMP.findall(text)) | set(JS_HOOK.findall(text))
    for name in sorted(names):
        pos = text.find(name)
        symbols.append({
            "name": name,
            "kind": "hook" if name.startswith("use") else ("component" if name[:1].isupper() else "symbol"),
            "path": rel(path),
            "line": text.count("\n", 0, max(pos, 0)) + 1,
            "qualname": name,
        })
    imports = [{"path": rel(path), "module": m.group(1), "line": text.count("\n", 0, m.start()) + 1} for m in JS_IMPORT.finditer(text)]
    return symbols, imports, sorted(set(URL.findall(text))), sorted(set(ENV_JS.findall(text)))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compact", action="store_true", help="omit per-file content hashes")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    file_index, symbols, imports, routes, configs, frontend = [], [], [], [], [], []
    fingerprint = hashlib.sha256()

    for path in iter_files():
        text = read_text(path)
        content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        fingerprint.update(rel(path).encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(content_hash.encode("ascii"))
        fingerprint.update(b"\n")

        row = {
            "path": rel(path),
            "size": len(text.encode("utf-8", errors="ignore")),
            "lines": text.count("\n") + 1,
            "ext": path.suffix.lower(),
        }
        if not args.compact:
            row["sha256"] = content_hash
        file_index.append(row)

        if path.suffix.lower() == ".py":
            s, i, r, c = py_index(path, text)
        elif path.suffix.lower() in FRONTEND_EXTS:
            s, i, r, c = js_index(path, text)
            frontend.extend(s)
        else:
            continue

        symbols.extend(s)
        imports.extend(i)
        routes.extend({"path": rel(path), "route": x} for x in r)
        configs.extend({"path": rel(path), "key": x} for x in c)

    file_index.sort(key=lambda x: x["path"])
    symbols.sort(key=lambda x: (x["name"].lower(), x["path"], x["line"]))
    imports.sort(key=lambda x: (x["path"], x["module"]))
    routes.sort(key=lambda x: (x["route"], x["path"]))
    configs.sort(key=lambda x: (x["key"], x["path"]))
    frontend.sort(key=lambda x: (x["name"].lower(), x["path"]))

    meta = {
        "schema_version": 2,
        "source_fingerprint_sha256": fingerprint.hexdigest(),
        "file_count": len(file_index),
        "symbol_count": len(symbols),
        "route_count": len(routes),
    }

    payloads = {
        "INDEX_META.json": meta,
        "FILE_INDEX.json": {"schema_version": 2, "files": file_index},
        "SYMBOL_INDEX.json": {"schema_version": 2, "symbols": symbols},
        "ROUTE_INDEX.json": {"schema_version": 2, "routes": routes},
        "IMPORT_INDEX.json": {"schema_version": 2, "imports": imports},
        "CONFIG_INDEX.json": {"schema_version": 2, "config_keys": configs},
        "FRONTEND_INDEX.json": {"schema_version": 2, "symbols": frontend},
    }

    for name, payload in payloads.items():
        (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(meta, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
