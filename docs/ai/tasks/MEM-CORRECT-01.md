# MEM-CORRECT-01 — Fix Memory error semantics and failure classification

**Order:** 7  
**Phase:** 1 Current hardening  
**Priority:** P0  
**Branch:** `fix/memory-error-semantics`  
**Depends on:** `BRAIN-01`

## Goal
Stop treating infrastructure/database failures as normal not-found or false business outcomes.

## Primary scope
- `backend/memory/app/services/chat_service.py`
- `backend/memory/app/services/message_service.py`
- `memory domain/repository error types`
- `Memory tests`

## Required behavior
- Catch domain not-found explicitly.
- Do not auto-create a chat because a DB lookup failed unexpectedly.
- Mutation methods distinguish no-op/not-found from database failure.
- RPC/Gateway error envelopes preserve bounded category without leaking internals.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Remove duplicated exception translation in touched Memory services and keep one domain-error mapping path.

## Non-goals
- No memory embedding/ranking changes.

## Validation
- Focused Memory error-contract tests
- Full Memory suite
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
