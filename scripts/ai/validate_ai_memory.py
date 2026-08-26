#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MEM=ROOT/"docs"/"ai"/"memory"
ID_RE=re.compile(r"^(DEC|FAIL|BUG|DEBT|CAP|CON)-\d{3,}$")
STRUCT=[("SERVICES.json","services"),("CAPABILITIES.json","capabilities"),("CONTRACTS.json","contracts"),("DECISIONS.json","decisions"),("FAILED_APPROACHES.json","approaches"),("BUGS.json","bugs"),("TECH_DEBT.json","items")]

def main():
    errors=[]; seen={}
    for filename,key in STRUCT:
        p=MEM/filename
        try: data=json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{filename}: invalid JSON: {exc}"); continue
        rows=data.get(key,[])
        if not isinstance(rows,list):
            errors.append(f"{filename}: `{key}` must be list"); continue
        for i,row in enumerate(rows):
            if not isinstance(row,dict): errors.append(f"{filename}[{i}]: object required"); continue
            rid=row.get("id")
            if rid:
                if filename!="SERVICES.json" and not ID_RE.match(str(rid)): errors.append(f"{filename}[{i}]: invalid id {rid}")
                if rid in seen: errors.append(f"duplicate id {rid}: {seen[rid]} and {filename}")
                seen[rid]=filename
            for field in ("canonical_paths","likely_locations","evidence"):
                vals=row.get(field)
                if not isinstance(vals,list): continue
                for value in vals:
                    if not isinstance(value,str): continue
                    if value.startswith(("backend/","frontend/","docs/","scripts/")) and "/" in value:
                        candidate=ROOT/value.split("#",1)[0]
                        # Directory paths are allowed; unresolved task/decision IDs are ignored.
                        if not candidate.exists(): errors.append(f"{filename}:{rid or i}: missing path {value}")
    hist=MEM/"CHANGE_HISTORY.jsonl"
    if hist.exists():
        for n,line in enumerate(hist.read_text(encoding="utf-8").splitlines(),1):
            if not line.strip(): continue
            try: json.loads(line)
            except Exception as exc: errors.append(f"CHANGE_HISTORY.jsonl:{n}: {exc}")
    handoff=MEM/"HANDOFF.md"
    if handoff.exists() and len(handoff.read_text(encoding="utf-8").splitlines())>140:
        errors.append("HANDOFF.md exceeds 140 lines")
    if errors:
        print("AI memory validation FAILED")
        for e in errors: print("-",e)
        return 1
    print(f"AI memory validation OK ({len(seen)} stable records)")
    return 0
if __name__=="__main__": raise SystemExit(main())
