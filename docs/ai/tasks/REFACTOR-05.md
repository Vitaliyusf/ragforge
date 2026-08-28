# REFACTOR-05 — Decompose memory_service.py

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


## Files
- `backend/memory/app/services/memory_service.py`
- new memory policy/retrieval/consolidation modules
- Memory tests

## FULL MEMORY SUITE
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/memory"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q
```

## LOCAL CHAT/MEMORY SMOKE
Run normal chat flow that loads/writes memory.

## OPTIONAL
Agent Memory60 only if semantics changed.

## DO NOT RUN
Full240.
