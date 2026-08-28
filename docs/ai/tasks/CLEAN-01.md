# CLEAN-01 — Remove confirmed dead compatibility code

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
- Use the repository's canonical Python 3.11 test toolchain.
- Do not weaken tests, mypy, Ruff, auth, security, or benchmark gates just to make them pass.
- Stop on any new unrelated failure and report it.


## Known candidates to inspect
- `backend/gateway/app/messaging/factories.py`
- `backend/gateway/app/messaging/implementations/rabbitmq.py`
- related messaging interfaces
- any additional candidate only after repo-wide reference search

## REQUIRED DISCOVERY — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
rg -n "MessageQueueFactory|messaging\.implementations\.rabbitmq|IProducer|IConsumer" backend
```

Also inspect route registration before deleting anything named `legacy`.

## LOCAL TEST — RUN BY CODEX
Run the complete suite of every affected service.

Example Gateway:
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/gateway"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q
```

## STATIC
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
ruff check backend/
git diff --check
```

## DO NOT RUN
Smoke30 unless a supposedly dead path is discovered to be on live RAG/LLM execution.

## STOP CONDITION
Only zero-reference / intentionally obsolete code removed.
