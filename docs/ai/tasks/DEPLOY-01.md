# DEPLOY-01 — Production deployment profile and stateful-service policy

**Order:** 53  
**Phase:** 7 Distributed production  
**Priority:** P2  
**Branch:** `chore/production-deployment-profile`  
**Depends on:** `SUPPLY-01`, `HEALTH-01`

## Goal
Define an honest production deployment profile distinct from local Compose without prematurely requiring Kubernetes.

## Primary scope
- `docker-compose.prod.yml`
- `Caddy/TLS`
- `secrets/config`
- `backup/restore docs`
- `runtime resources`

## Required behavior
- Document managed/replicated stateful-service expectations.
- Define backup/restore and restore-test cadence.
- Use production-safe secret/config injection.
- Use readiness for stateless rollout.
- Remove unnecessary runtime egress where artifacts are baked.
- Pin release artifacts.
- Do not require Kubernetes unless environment requires it.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** No refactor.

## Non-goals
- No product feature work.

## Validation
- Prod config validation
- Documented/tested restore procedure where feasible

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
