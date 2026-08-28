# AGENT-02 — Typed Memory agent tool protocol and deterministic termination

**Order:** 40  
**Phase:** 5 Memory V2  
**Priority:** P2  
**Branch:** `refactor/memory-agent-tool-protocol`  
**Depends on:** `AGENT-01`

## Goal
Replace loose tool payload parsing/termination with versioned typed tool contracts.

## Primary scope
- `memory_agent.py`
- `tool schemas`
- `LLM typed execution`
- `tests`

## Required behavior
- Typed tool request/response schemas.
- Bound max steps/timeouts.
- Deterministic done semantics.
- No raw unvalidated fallback payloads.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Keep one agent loop; no parallel protocol versions.

## Non-goals
- No new agent framework.

## Validation
- Agent protocol tests

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
