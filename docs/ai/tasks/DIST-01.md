# DIST-01 — Canonical turn persistence with transactional outbox

**Order:** 48  
**Phase:** 7 Distributed production  
**Priority:** P2  
**Branch:** `feat/conversation-outbox`  
**Depends on:** `CHAT-01`

## Goal
Make critical completed-turn/domain-event persistence robust to crashes between database write and event publication.

## Primary scope
- `turn/history persistence owner`
- `Mongo outbox`
- `publisher worker`
- `idempotency/tests`

## Required behavior
- Write canonical state + outbox event atomically where supported.
- Publish unsent events idempotently.
- Lease/mark sent safely.
- Recover after crash at each boundary.
- Define effectively-once side effects; do not claim exactly-once.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Keep outbox domain-owned until reuse is proven.

## Non-goals
- No generic outbox framework unless multiple domains need it.

## Validation
- Outbox state-machine tests
- Integration crash simulation

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
