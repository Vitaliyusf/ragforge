# SEC-03 — Run application containers as non-root

**Order:** 9  
**Phase:** 1 Current hardening  
**Priority:** P1  
**Branch:** `fix/non-root-containers`  
**Depends on:** `HEALTH-01`

## Goal
Harden application containers with non-root users and minimal runtime privileges without breaking required writable paths or GPU execution.

## Primary scope
- `backend/*/Dockerfile`
- `frontend/Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`

## Required behavior
- Create dedicated non-root users for app containers where compatible.
- Make writable dirs explicit.
- Add no-new-privileges and capability dropping where safe.
- Treat vLLM/GPU separately.
- Document justified root exceptions.
- Preserve Qdrant unprivileged behavior.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Remove obsolete Dockerfile comments/instructions in touched files; do not mix dependency modernization.

## Non-goals
- No Kubernetes migration and no unrelated image upgrades.

## Validation
- Changed image builds
- Compose config
- Health + minimal chat/ingestion smoke

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
