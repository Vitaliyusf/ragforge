# RAG-02 — Bounded parallel subquery retrieval

## Execution location

**RUN BY:** Codex locally on the user's machine.

**REPOSITORY ROOT:**
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
```

## Global rules

- Do not reset, stash, clean, revert, or switch branches.
- Do not commit or push unless explicitly requested.
- Inspect current code before editing.
- TEST WHAT CHANGED. LET CI TEST THE REPOSITORY.
- Use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Do not weaken tests, mypy, Ruff, auth, security, or benchmark gates just to make them pass.
- Stop on any new unrelated failure and report it.


## Files to inspect
- `backend/rag/app/services/conversation_graph.py`
- retrieval/backend client code
- RAG concurrency tests

## DISCOVERY
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
rg -n "rewrite|decompose|subquery|gather|TaskGroup|retrieve" backend/rag/app/services backend/rag/app/tests
```

## LOCAL FOCUSED TEST
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/rag"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q -k "rewrite or decompose or subquery or concurrency or retrieval"
```

Tests must prove:
- actual overlap under artificial delay
- max concurrency bound
- deterministic merge regardless of completion order

## FULL RAG SUITE
```powershell
pytest app/tests -q
```

## LOCAL DOCKER BENCHMARK 1
Smoke30 regular.

## LOCAL DOCKER BENCHMARK 2
Repository-supported Extended/extended comparison benchmark.

Compare retrieval/E2E p50/p95 and downstream saturation.

## DO NOT RUN
Full240.
