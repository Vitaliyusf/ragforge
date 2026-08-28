# FILES-01 — Fix Mongo transaction fallback semantics

**Order:** 6  
**Phase:** 1 Current hardening  
**Priority:** P0  
**Branch:** `fix/files-transaction-fallback`  
**Depends on:** `BRAIN-01`

## Goal
Make the Files transaction context yield exactly once and never replay caller code after a transaction has started.

## Primary scope
- `backend/files/app/db/_base.py`
- `transaction callers`
- `Files DB tests`

## Required behavior
- Determine transaction support before caller block where possible.
- Yield exactly once.
- If a started transaction fails, propagate to an explicit operation retry boundary.
- Standalone Mongo fallback remains deterministic.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Simplify transaction/session helper branching while touched; do not add another transaction abstraction.

## Non-goals
- No ingestion redesign.

## Validation
- Focused transaction tests
- Full Files suite
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
