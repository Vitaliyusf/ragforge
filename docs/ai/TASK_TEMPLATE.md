# TASK-ID — Short Title

**Order:** N
**Phase:** X
**Priority:** P0/P1/P2/P3
**Branch:** `type/short-name`
**Depends on:** `TASK-X`, ...

## Goal
One observable outcome.

## Primary scope
- exact domain files/direct callers/tests

## Required behavior
- observable requirements

## Local refactor budget
- Improve readability only inside code this task already touches.
- If a touched production hotspot is >500 lines, inspect whether the changed concern can be extracted.
- At most 2 cohesive new production modules unless explicitly required.
- Prefer deleting replaced/legacy code to adding wrappers.
- Give each new file one clear domain responsibility and owner.
- No generic `utils/helpers/manager/common/misc/v2` dumping grounds.
- No unrelated cross-domain refactor.
- Remove stale narrative comments; keep invariants/WHY.
- Report files added/deleted, before/after hotspot line counts, legacy paths removed and new dependencies.

## Task-specific refactor target
Name the exact concern that may be extracted/simplified.

## Non-goals
Only realistic scope traps.

## Validation
- focused tests during iteration
- affected service suite once near completion only when cross-cutting/high-risk
- Ruff / diff
- mypy only when relevant
- benchmark only when semantics require it

## Measurement
Only for quality/performance work.

## Execution rules
- Current source wins.
- Preserve unrelated dirty files.
- No reset/stash/revert/clean.
- No commit/push.
- No generic doctor gate.
- Do not repair `.venv`.
- Use isolated uv Python 3.11 when local environment is unsuitable.
- Preserve the matching CI lane's canonical environment; extra dependencies make a
  result `NON-AUTHORITATIVE / ENVIRONMENT-ADJUSTED`, not `PASS`.
- Use one workspace-local uv cache and at most one corrected retry per environment
  root cause before reporting `BLOCKED`.
- Run any authoritative static-analysis scope intersected by changed files once
  before completion; do not substitute a narrower file-by-file scope.
- After the final diff audit and last source/test edit, record handoff once, rebuild
  the brain once and validate memory once.

## Final complexity report
Every task reports:

```text
production files added:
production files deleted:
hotspot before/after lines:
legacy/duplicate paths removed:
new dependencies:
```
