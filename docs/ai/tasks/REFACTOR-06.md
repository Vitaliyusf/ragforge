# REFACTOR-06 — Decompose eval_runner.py and eval_store.py

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
- `backend/rag/app/services/eval_runner.py`
- `backend/rag/app/services/eval_store.py`
- new eval dataset/run/scoring/repository helpers
- benchmark/eval tests

## LOCAL FOCUSED TEST
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/rag"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q -k "eval or benchmark or dataset or manifest or export"
```

## FULL RAG SUITE
```powershell
pytest app/tests -q
```

## OPTIONAL
Smoke30 only if benchmark execution wiring changed.

## DO NOT RUN
Full240.
