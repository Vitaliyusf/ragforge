# HEALTH-01 — Standardize liveness and readiness contracts

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Order:** 8  
**Phase:** 1 Current hardening  
**Priority:** P1  
**Branch:** `fix/service-health-readiness`  
**Depends on:** `BRAIN-01`

## Goal
Give every service truthful `/live` and `/ready` semantics so orchestration never routes traffic to a process that is alive but unable to serve its primary workload.

## Primary scope
- `backend service health routes/runtime state`
- `docker-compose.yml`
- `Health UI`
- `health tests`

## Required behavior
- `/live` checks process liveness only.
- `/ready` returns 200 only when critical dependencies for primary workload are ready; otherwise 503.
- Remove hard-coded connected=true fields.
- Add Qdrant Compose healthcheck and use `service_healthy` where appropriate.
- Frontend distinguishes live vs ready.
- Do not make liveness depend on every downstream.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Use runtime-owned health snapshots instead of adding more module globals.

## Non-goals
- No deployment-platform migration.

## Validation
- Focused health tests
- Frontend Health tests
- docker compose config --quiet
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
