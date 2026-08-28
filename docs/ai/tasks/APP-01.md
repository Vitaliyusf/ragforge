# APP-01 — Residual ApplicationRuntime and lifecycle consolidation

**Order:** 21  
**Phase:** 2 Simplification  
**Priority:** P2  
**Branch:** `refactor/service-runtime-containers`  
**Depends on:** `EMBED-01`, `FILES-02`, `LLM-CTRL-01`, `CHAT-01`

## Goal
Finish explicit lifespan-owned runtime/dependency ownership only for services that still rely on fragile mutable module globals after domain tasks.

## Primary scope
- `remaining service main.py/deps/runtime modules`
- `FastAPI lifespan/tests`

## Required behavior
- Use app.state.runtime or equivalent explicit ownership.
- No import-time network/database connection.
- One startup/shutdown owner for clients/consumers/threads.
- Dependencies read runtime-owned objects.
- Do not refactor already-clean services solely for uniformity.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Residual task only; most service-local lifecycle cleanup should happen inside domain tasks.

## Non-goals
- No repo-wide rewrite.

## Validation
- Affected service suites
- Lifecycle/shutdown/readiness tests
- Ruff

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
