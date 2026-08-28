# PROV-01 — Close benchmark build/runtime provenance

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
- `backend/rag/app/services/benchmark_manifest.py`
- `backend/rag/app/services/benchmark_comparison.py`
- benchmark export/provenance tests
- Docker build args / labels / `.env.example`
- scripts that stamp build identity

## Required behavior
Record truthfully:
- source git SHA
- branch when known
- dirty state
- deterministic source fingerprint when dirty
- build timestamp
- image identity/tag when observable
- actual vLLM runtime identity/config

Never export secrets, raw diffs, `.env`, logs, benchmark ZIP contents, caches, `.venv`, or node_modules.

## LOCAL FOCUSED TEST — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/rag"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q -k "manifest or provenance or comparison or export"
```

## LOCAL FULL RAG SUITE — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/rag"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q
```

## LOCAL STATIC CHECKS — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
ruff check backend/rag backend/shared
mypy backend/shared backend/gateway/app --config-file mypy.ini
git diff --check
docker compose config
```

## DO NOT RUN
- Smoke30
- Retrieval220
- Full240

## STOP CONDITION
A future benchmark artifact can no longer claim the same source identity for materially different dirty source trees.
