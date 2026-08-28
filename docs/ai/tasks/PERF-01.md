# PERF-01 — Remove blocking persistence from async RAG hot path

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
- `backend/rag/app/services/conversation_persistence.py`
- `backend/rag/app/services/conversation_graph.py`
- persistence/checkpoint tests

## DISCOVERY
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
rg -n "MongoClient|time\.sleep|load_context\(|save_turn\(|save_thread\(|save_summary\(|save_checkpoint\(" backend/rag
```

## Required behavior
Make the persistence boundary awaitable via stable async driver support or one bounded offload adapter. Do not scatter ad-hoc `to_thread()` calls across graph nodes.

## LOCAL FOCUSED TEST — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/rag"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q -k "persistence or checkpoint or context or resume"
```

Add/execute controlled-delay tests proving the event loop continues while persistence is delayed.

## LOCAL FULL RAG SUITE
```powershell
pytest app/tests -q
```

## LOCAL DOCKER CHAT SMOKE
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
docker compose exec -T frontend node < tests/smoke_chat.js
```

## LOCAL DOCKER BENCHMARK
Smoke30.

Compare to accepted interactivity baseline:
- wall
- queue p95
- TTFT p50/p95
- E2E p95
- errors

## DO NOT RUN
Retrieval220 unless retrieval behavior changed.
Full240 never here.
