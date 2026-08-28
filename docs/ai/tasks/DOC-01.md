# DOC-01 — Align docs with actual runtime

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
- `README.md`
- relevant operator/security/runtime docs

## Required change
Document effective defaults vs optional capabilities.
Correct stale claims such as test counts/runtime defaults/reranker state.

## TEST
No automated test required.

RUN BY CODEX:
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
git diff --check
```

Manually verify referenced commands/paths exist.

## DO NOT RUN
Any benchmark.
