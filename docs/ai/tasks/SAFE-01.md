# SAFE-01 — Fail-closed streaming output safety

**Order:** 5  
**Phase:** 1 Current hardening  
**Priority:** P0  
**Branch:** `fix/streaming-output-guardrail`  
**Depends on:** `RAG-03`

## Goal
Guarantee that blocked model output emits zero unsafe token events to the browser.

## Primary scope
- `RAG generation/events/output-guard flow`
- `frontend stream contract if needed`
- `safety/stream tests`

## Required behavior
- No user-visible token crosses the trust boundary before required approval.
- Blocked output emits zero unsafe token events.
- Approved output remains coherent and citations remain correct.
- Cancellation/timeouts are bounded.
- Document TTFT semantics after the safety change.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Extract output approval/emission policy from conversation_graph.py if it replaces inline branching.

## Non-goals
- No FRONT-01 render optimization in this task.

## Validation
- Focused safety/stream tests
- Full RAG suite
- Frontend tests if stream contract changes
- Ruff
- git diff --check

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
