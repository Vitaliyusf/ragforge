# REFACTOR-04 — Decompose file_ingestion_graph.py

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
- `backend/files/app/services/file_ingestion_graph.py`
- new extraction/review/chunking/indexing/rollback modules
- Files tests

## FULL FILES SUITE
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/files"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q
```

## LOCAL DOCKER INGESTION SMOKE
Run authenticated ingestion smoke.

## DO NOT RUN
Smoke30 / Full240.
