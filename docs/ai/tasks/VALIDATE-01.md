# VALIDATE-01 — Baseline hardening release gate

**Order:** 13  
**Phase:** 1 Current hardening  
**Priority:** P0  
**Branch:** `release/baseline-validation-v1`  
**Depends on:** `DEPS-01`

## Goal
Establish an authoritative Baseline V1 before changing document, index and retrieval semantics.

## Primary scope
- `CI`
- `frontend build`
- `security/dependency scans`
- `Compose`
- `chat/ingestion`
- `Smoke30`
- `Retrieval220`
- `Full240`
- `runtime provenance`

## Required behavior
- Run clean CI and frontend production build.
- Validate Compose and service readiness.
- Run chat and ingestion smoke.
- Run Smoke30, exact recovered Retrieval220 and Full240 on provenance-complete runtime.
- Archive benchmark manifests/exports and accepted baseline.
- Do not change code inside validation.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** No refactoring; validation only.

## Non-goals
- No feature or refactor work.

## Validation
- All release gates pass or explicit blocker task is created
- Baseline artifacts have compatible source/runtime/dataset provenance

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
