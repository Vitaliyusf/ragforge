# EMBED-01 — Canonicalize embedding runtime and retire legacy paths

**Order:** 14  
**Phase:** 2 Simplification  
**Priority:** P1  
**Branch:** `refactor/embedding-runtime`  
**Depends on:** `VALIDATE-01`

## Goal
Reduce Embedding to one canonical query/passage embedding boundary and one typed ingestion job path.

## Primary scope
- `backend/embedding/app`
- `topics/callers`
- `Docker requirements`
- `shared retry/DLQ imports`

## Required behavior
- Prove active handlers/topics.
- Keep one query embedding path and one typed passage/job path.
- Move/remove extraction responsibility as DOCPIPE work enables.
- Remove duplicate handlers and inactive chunking after caller migration.
- Replace importlib shared-module hacks with safe imports.
- Use lifecycle-owned clients/consumers.
- Remove unused adapters/dependencies.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Absorbs the Embedding portion of old refactor work; prefer deletion over wrappers.

## Non-goals
- No embedding-model change.

## Validation
- Embedding focused tests
- Full Embedding suite
- Affected integration smoke
- Ruff
- Image build if deps change

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
