# DIST-03 — Distributed tenant-aware rate limiting when Gateway scales out

**Order:** 50  
**Phase:** 7 Distributed production  
**Priority:** P3  
**Branch:** `feat/distributed-rate-limits`  
**Depends on:** `DEPLOY-01`

## Goal
Replace process-local quotas only when multiple Gateway replicas make local counters incorrect.

## Primary scope
- `Gateway rate limiter`
- `shared distributed backend`
- `deployment/tests`

## Required behavior
- Gate task on real multi-replica deployment.
- Use shared atomic store/algorithm.
- Preserve tenant/user scoping and bounded dependency timeout.
- Define fail-open/fail-closed policy explicitly.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Conditional task; no speculative Redis adoption.

## Non-goals
- Skip while Gateway is intentionally single-replica.

## Validation
- Two-Gateway shared-quota integration test

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
