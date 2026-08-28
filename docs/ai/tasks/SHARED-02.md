# SHARED-02 — Consolidate proven cross-cutting contracts without a shared god module

**Order:** 11  
**Phase:** 1 Current hardening  
**Priority:** P1  
**Branch:** `refactor/shared-contracts-v2`  
**Depends on:** `TEST-01`

## Goal
Centralize only dangerous cross-service invariants that are already duplicated while shrinking legacy compatibility surfaces.

## Primary scope
- `backend/shared`
- `direct service imports/tests`
- `message schemas`
- `logging/redaction`
- `metrics setup`

## Required behavior
- Make shared modules safe to import without duplicate metric-registration side effects.
- Centralize auth tickets, context, redaction, error envelopes, broker envelopes/version helpers and security middleware only where duplication is proven.
- Retire legacy schemas after caller migration.
- Keep domain logic out of shared.
- Prefer direct submodule imports over eager package import fan-out.
- Remove compatibility exports after zero-reference proof.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Goal is fewer shared paths, not more abstractions.

## Non-goals
- No new shared framework for RAG/Memory/Files business logic.

## Validation
- Shared suite
- Affected service contract tests
- Ruff
- mypy on shared
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
