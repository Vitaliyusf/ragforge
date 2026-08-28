# REFACTOR-02 — Decompose LLMService.execute

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
- `backend/llm_agent/app/services/llm_service.py`
- new cohesive llm_agent modules
- llm_agent tests

## LOCAL FOCUSED TEST
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/llm_agent"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q -k "execute or structured or citation or stream or provider or vllm"
```

## FULL LLM_AGENT SUITE
```powershell
pytest app/tests -q
```

## LOCAL DOCKER BENCHMARK
Smoke30.

## HARD RULE
Behavior-neutral extraction only. No prompt/schema/token/runtime changes.

## DO NOT RUN
Full240.
