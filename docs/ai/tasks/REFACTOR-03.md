# REFACTOR-03 — Decompose conversation_graph.py

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
- `backend/rag/app/services/conversation_graph.py`
- new cohesive graph/node/checkpoint/metrics modules
- RAG tests

## LOCAL FOCUSED TEST
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/rag"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q -k "graph or checkpoint or retrieval or generate or evaluate or persist"
```

## FULL RAG SUITE
```powershell
pytest app/tests -q
```

## LOCAL DOCKER BENCHMARK
Smoke30.

## HARD RULE
Move/extract only. No semantic change.

## DO NOT RUN
Retrieval220 / Full240.
