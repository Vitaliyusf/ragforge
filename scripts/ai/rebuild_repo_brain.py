#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, hashlib, json, re, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "ai" / "generated"
SKIP = {".git",".next","node_modules","__pycache__",".pytest_cache",".mypy_cache",".ruff_cache",".venv","venv","coverage","dist","build","logs","qdrant_storage","uploads"}
TEXT = {".py",".js",".jsx",".ts",".tsx",".json",".yml",".yaml",".toml",".md"}
FRONT = {".js",".jsx",".ts",".tsx"}
FASTAPI = re.compile(r"(?P<router>[A-Za-z_][\w\.]*)\.(?P<method>get|post|put|patch|delete|options|head|websocket)\(\s*[\"'](?P<path>[^\"']+)")
JS_EXPORT = re.compile(r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)")
JS_FUNC = re.compile(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")
JS_COMP = re.compile(r"\b(?:export\s+)?const\s+([A-Z][A-Za-z0-9_$]*)\s*=\s*(?:memo\()?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")
JS_HOOK = re.compile(r"\b(?:export\s+)?(?:const\s+)?(use[A-Z][A-Za-z0-9_$]*)\b")
JS_IMPORT = re.compile(r"\bimport\b[\s\S]*?\bfrom\s+[\"']([^\"']+)[\"']")
ENV_PY = re.compile(r"(?:os\.getenv|os\.environ\.get)\(\s*[\"']([A-Z0-9_]+)[\"']")
ENV_JS = re.compile(r"process\.env\.([A-Z0-9_]+)")
URL = re.compile(r"[\"'](/v\d+/[^\"']*)[\"']")

def git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git",*args],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None

def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()

def files() -> Iterable[Path]:
    for p in ROOT.rglob("*"):
        if not p.is_file() or any(part in SKIP for part in p.parts):
            continue
        if p.suffix.lower() not in TEXT or "docs/ai/generated" in p.as_posix():
            continue
        yield p

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8",errors="replace")

def py_index(p: Path, text: str):
    syms, imps, routes, cfg = [], [], [], sorted(set(ENV_PY.findall(text)))
    try: tree = ast.parse(text)
    except SyntaxError: return syms,imps,routes,cfg
    stack=[]
    class V(ast.NodeVisitor):
        def visit_ClassDef(self,node):
            syms.append({"name":node.name,"kind":"class","path":rel(p),"line":node.lineno,"qualname":".".join(stack+[node.name])})
            stack.append(node.name); self.generic_visit(node); stack.pop()
        def _fn(self,node):
            syms.append({"name":node.name,"kind":"method" if stack else "function","path":rel(p),"line":node.lineno,"qualname":".".join(stack+[node.name])})
            stack.append(node.name); self.generic_visit(node); stack.pop()
        visit_FunctionDef=_fn
        visit_AsyncFunctionDef=_fn
        def visit_Import(self,node):
            for a in node.names: imps.append({"path":rel(p),"module":a.name,"line":node.lineno})
        def visit_ImportFrom(self,node):
            imps.append({"path":rel(p),"module":"."*node.level+(node.module or ""),"line":node.lineno})
    V().visit(tree)
    for m in FASTAPI.finditer(text): routes.append(f"{m.group('method').upper()} {m.group('path')}")
    return syms,imps,sorted(set(routes)),cfg

def js_index(p: Path,text: str):
    syms=[]
    names=set(JS_EXPORT.findall(text))|set(JS_FUNC.findall(text))|set(JS_COMP.findall(text))|set(JS_HOOK.findall(text))
    for name in sorted(names):
        pos=text.find(name)
        syms.append({"name":name,"kind":"hook" if name.startswith("use") else ("component" if name[:1].isupper() else "symbol"),"path":rel(p),"line":text.count("\n",0,max(pos,0))+1,"qualname":name})
    imps=[{"path":rel(p),"module":m.group(1),"line":text.count("\n",0,m.start())+1} for m in JS_IMPORT.finditer(text)]
    return syms,imps,sorted(set(URL.findall(text))),sorted(set(ENV_JS.findall(text)))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--compact",action="store_true"); args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    file_index=[]; symbols=[]; imports=[]; routes=[]; configs=[]; frontend=[]
    for p in files():
        text=read(p)
        row={"path":rel(p),"size":len(text.encode("utf-8")),"lines":text.count("\n")+1,"ext":p.suffix.lower()}
        if not args.compact: row["sha1"]=hashlib.sha1(text.encode("utf-8",errors="ignore")).hexdigest()
        file_index.append(row)
        if p.suffix.lower()==".py":
            s,i,r,c=py_index(p,text)
        elif p.suffix.lower() in FRONT:
            s,i,r,c=js_index(p,text); frontend.extend(s)
        else:
            continue
        symbols.extend(s); imports.extend(i)
        routes.extend({"path":rel(p),"route":x} for x in r)
        configs.extend({"path":rel(p),"key":x} for x in c)
    file_index.sort(key=lambda x:x["path"]); symbols.sort(key=lambda x:(x["name"].lower(),x["path"],x["line"]))
    imports.sort(key=lambda x:(x["path"],x["module"])); routes.sort(key=lambda x:(x["route"],x["path"]))
    configs.sort(key=lambda x:(x["key"],x["path"])); frontend.sort(key=lambda x:(x["name"].lower(),x["path"]))
    status=git("status","--porcelain")
    meta={"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"git_sha":git("rev-parse","HEAD"),"branch":git("branch","--show-current"),"dirty":bool(status) if status is not None else None,"file_count":len(file_index),"symbol_count":len(symbols),"route_count":len(routes)}
    payloads={
        "INDEX_META.json":meta,
        "FILE_INDEX.json":{"schema_version":1,"files":file_index},
        "SYMBOL_INDEX.json":{"schema_version":1,"symbols":symbols},
        "ROUTE_INDEX.json":{"schema_version":1,"routes":routes},
        "IMPORT_INDEX.json":{"schema_version":1,"imports":imports},
        "CONFIG_INDEX.json":{"schema_version":1,"config_keys":configs},
        "FRONTEND_INDEX.json":{"schema_version":1,"symbols":frontend},
    }
    for name,data in payloads.items():
        (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(meta,indent=2))
if __name__=="__main__": main()
