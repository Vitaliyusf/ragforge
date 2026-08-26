#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
MEM=ROOT/"docs"/"ai"/"memory"; GEN=ROOT/"docs"/"ai"/"generated"
STOP={"the","a","an","and","or","to","of","in","for","is","it","on","with","this","that","אני","את","של","זה","אם","על","עם","לא"}

def toks(s): return [x for x in re.findall(r"[\w./:@+-]+",s.lower(),flags=re.UNICODE) if len(x)>1 and x not in STOP]
def flat(x:Any)->str:
    if isinstance(x,dict): return " ".join(str(k)+" "+flat(v) for k,v in x.items())
    if isinstance(x,list): return " ".join(flat(v) for v in x)
    return "" if x is None else str(x)
def score(q,text):
    low=text.lower(); total=0.0
    for t in q:
        n=low.count(t)
        if n:
            total+=min(n,5)
            if re.search(rf"\b{re.escape(t)}\b",low): total+=1.5
    return total
def records(path):
    try: data=json.loads(path.read_text(encoding="utf-8"))
    except Exception: return []
    if isinstance(data,list): return [{"_value":x} for x in data]
    if not isinstance(data,dict): return [{"_value":data}]
    lists=[(k,v) for k,v in data.items() if isinstance(v,list)]
    if lists:
        k,v=max(lists,key=lambda kv:len(kv[1]))
        return [{"_collection":k,**(x if isinstance(x,dict) else {"_value":x})} for x in v]
    return [data]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("query"); ap.add_argument("--top",type=int,default=20); a=ap.parse_args()
    q=toks(a.query)
    if not q: raise SystemExit("No useful query tokens.")
    out=[]
    for p in sorted(MEM.glob("*")):
        if p.suffix==".json":
            for row in records(p):
                txt=flat(row); s=score(q,txt)
                if s:
                    label=row.get("id") or row.get("name") or row.get("title") or "record"
                    out.append((s+2,f"{p.relative_to(ROOT)}::{label}",txt[:700]))
        elif p.suffix in {".md",".jsonl"}:
            for ln,line in enumerate(p.read_text(encoding="utf-8",errors="replace").splitlines(),1):
                s=score(q,line)
                if s: out.append((s+1,f"{p.relative_to(ROOT)}:{ln}",line[:700]))
    for name in ["SYMBOL_INDEX.json","ROUTE_INDEX.json","CONFIG_INDEX.json","FILE_INDEX.json","FRONTEND_INDEX.json"]:
        p=GEN/name
        if not p.exists(): continue
        for row in records(p):
            txt=flat(row); s=score(q,txt)
            if s:
                label=row.get("qualname") or row.get("name") or row.get("route") or row.get("key") or row.get("path") or "record"
                out.append((s,f"{p.relative_to(ROOT)}::{label}",txt[:700]))
    out.sort(key=lambda x:(-x[0],x[1]))
    for s,w,e in out[:max(1,a.top)]:
        print(f"[{s:.1f}] {w}\n  {e}")
    if not out: print("No brain/index matches. Use targeted source grep next.")
if __name__=="__main__": main()
