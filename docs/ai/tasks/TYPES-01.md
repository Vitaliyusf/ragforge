# TYPES-01 — Strengthen critical contracts incrementally

**Order:** 22  
**Phase:** 2 Simplification  
**Priority:** P2  
**Branch:** `refactor/typed-contracts`  
**Depends on:** `APP-01`

## Goal
Expand strict typing across high-risk boundaries after architecture simplification.

## Primary scope
- `RAG/eval/memory/vector/files critical schemas`
- `mypy config`
- `frontend socket/API JSDoc/TS islands`

## Required behavior
- Move one service/boundary at a time into stricter typing.
- Prefer typed models over Dict[str,Any] at boundaries.
- Do not force full TypeScript rewrite.
- Focus on risk-bearing contracts, not cosmetic annotations.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Use types to simplify contracts; do not create adapter classes solely for the type checker.

## Non-goals
- No repo-wide strict switch.

## Validation
- Targeted mypy
- Affected tests
- Frontend type/JSDoc tests where applicable

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
