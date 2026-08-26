#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MEM=ROOT/"docs"/"ai"/"memory"
def git(*args):
    try: return subprocess.check_output(["git",*args],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except Exception: return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--agent",choices=["codex","claude","human"],required=True)
    ap.add_argument("--task",default=None); ap.add_argument("--summary",required=True)
    ap.add_argument("--result",choices=["completed","partial","blocked"],default="completed")
    ap.add_argument("--files",nargs="*",default=[]); ap.add_argument("--tests",nargs="*",default=[])
    ap.add_argument("--memory-ids",nargs="*",default=[]); ap.add_argument("--unresolved",nargs="*",default=[])
    ap.add_argument("--next",dest="next_step",default=""); ap.add_argument("--safe-for-commit",choices=["yes","no"],default="no")
    a=ap.parse_args(); branch=git("branch","--show-current"); sha=git("rev-parse","HEAD"); now=datetime.now(timezone.utc).isoformat()
    row={"ts":now,"agent":a.agent,"task":a.task,"branch":branch,"head":sha,"summary":a.summary,"files":a.files,"tests":a.tests,"memory_ids":a.memory_ids,"result":a.result}
    with (MEM/"CHANGE_HISTORY.jsonl").open("a",encoding="utf-8") as f: f.write(json.dumps(row,ensure_ascii=False)+"\n")
    def bullets(xs): return "\n".join(f"- {x}" for x in xs) if xs else "- None"
    text=f"""# Latest Handoff

- Task: {a.task or 'untracked'}
- Agent: {a.agent}
- Branch: {branch or 'unknown'}
- HEAD: {sha or 'unknown'}
- Status: {a.result}
- Timestamp: {now}
- Safe for manual commit: {a.safe_for_commit}

## What changed
{a.summary}

## Files touched
{bullets([f'`{x}`' for x in a.files])}

## Tests/checks
{bullets(a.tests)}

## Memory records
{bullets(a.memory_ids)}

## Unresolved
{bullets(a.unresolved)}

## Next recommended step
{a.next_step or 'None recorded'}
"""
    (MEM/"HANDOFF.md").write_text(text,encoding="utf-8")
    print("Recorded shared history and handoff.")
if __name__=="__main__": main()
