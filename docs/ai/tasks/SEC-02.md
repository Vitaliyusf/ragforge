# SEC-02 — Fail closed for required security components

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
- `backend/gateway/app/main.py`
- `backend/shared/security.py`
- `backend/shared/rate_limiter.py`
- Gateway config/tests

## Required behavior
Mandatory production security components must not disappear because of ImportError/build drift.
Telemetry may remain optional.

## LOCAL FOCUSED TEST — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/gateway"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q -k "security or auth or rate or middleware or startup"
```

## LOCAL FULL GATEWAY SUITE — RUN BY CODEX
```powershell
pytest app/tests -q
```

## LOCAL STACK TEST — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
docker compose config
docker compose up -d gateway
docker compose ps
```
Verify normal startup and production-like misconfiguration fails closed.

## DO NOT RUN
Smoke30 / Retrieval220 / Full240.

## STOP CONDITION
Gateway cannot silently start in production without required security boundary.
