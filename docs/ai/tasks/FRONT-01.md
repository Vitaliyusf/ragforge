# FRONT-01 — Batch chat streaming renders and shrink ChatContext responsibility

**Order:** 18  
**Phase:** 2 Simplification  
**Priority:** P1  
**Branch:** `perf/chat-stream-rendering`  
**Depends on:** `CHAT-01`

## Goal
Reduce React work from token-by-token state updates and locally decompose the Chat runtime while preserving one clear public façade.

## Primary scope
- `frontend/src/features/chat/context/ChatContext.jsx`
- `chatReducers.js`
- `socketService.js`
- `chat hooks/components/tests`

## Required behavior
- Buffer streaming text and flush at requestAnimationFrame or 25–50ms cadence.
- Flush immediately on terminal/error/cancel.
- Preserve token order/final text/citations.
- Extract changed runtime concerns into cohesive hooks/services.
- Keep one authoritative streaming-text source.
- Do not add another global state framework.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Explicitly allowed to perform local ChatContext refactor instead of deferring to a separate REFACTOR task.

## Non-goals
- No backend persistence redesign.

## Validation
- Focused chat tests
- Frontend full tests
- Production build
- Synthetic token-burst render/update measurement

## Measurement
- State updates/renders, main-thread time, final text correctness.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
