# CLEAN-03 — Pydantic v2 config cleanup

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
- `backend/rag/app/core/config.py`
- `backend/rag/app/schemas/rag.py`
- scoped search for `class Config:` in touched RAG config/schema modules

## Required change
Use `ConfigDict` / `SettingsConfigDict` while preserving defaults, env behavior, schema examples and validation.

## LOCAL FOCUSED TEST — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/rag"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q -k "config or schema"
```

## LOCAL FULL RAG SUITE — RUN BY CODEX
```powershell
pytest app/tests -q
```

## STATIC
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
ruff check backend/rag
```

## DO NOT RUN
Smoke30 / Retrieval220 / Full240.

## STOP CONDITION
Warnings removed, behavior unchanged, full RAG suite green.
