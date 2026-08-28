# CONFIG-01 — Make runtime configuration honest and deployment-owned

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Order:** 3  
**Phase:** 1 Current hardening  
**Priority:** P0  
**Branch:** `fix/runtime-config-control-plane`  
**Depends on:** `BRAIN-01`

## Goal
Align accepted runtime defaults and remove or correctly implement controls that currently claim to mutate behavior they do not actually control.

## Primary scope
- `docker-compose.yml`
- `.env.example`
- `backend/llm_agent/app/services/config_service.py`
- `backend/llm_agent/app/messaging/config_handler.py`
- `backend/gateway/app/rest/v1/config.py`
- `frontend/src/features/config`
- `frontend/src/components/layout/Header.jsx`

## Required behavior
- Align accepted answer-evaluation structured-output default to `json_schema`.
- Prefer deployment-owned configuration for the current product; UI may show effective config but must not claim successful live mutation when none happened.
- Remove unsupported vLLM/Ollama URL edits or implement them end-to-end.
- Fix/remove generation-parameter action mismatch.
- Remove fake runtime switching or implement validate→health-check→atomic swap→audit→rollback.
- Unknown config fields must fail explicitly.
- Frontend/Gateway/LLM request shapes must match.
- Document live-effective vs restart-required settings.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Delete dead runtime-switch/config plumbing if zero-reference proof supports it; thin repetitive route error wrappers while touched.

## Non-goals
- No vLLM performance retuning and no new provider framework.

## Validation
- Focused Config/Model contract tests across frontend/Gateway/llm_agent
- Affected service suites
- Frontend tests/build if UI changes
- Ruff
- git diff --check

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
