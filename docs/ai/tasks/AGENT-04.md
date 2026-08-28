# AGENT-04 — Tenant-scoped general agent mode

**Order:** 42  
**Phase:** 5 Memory V2  
**Priority:** P3  
**Branch:** `feat/rag-agent-mode`  
**Depends on:** `AGENT-03`, `RAG-06`

## Goal
Optionally add a general tool-using RAG agent only after deterministic RAG and Memory agent baselines are strong.

## Primary scope
- `RAG agent mode`
- `tool registry/policy`
- `auth`
- `eval`

## Required behavior
- Start read-only.
- Every tool enforces server-side tenant policy.
- Bound steps/time/cost.
- Keep deterministic Regular/Extended modes.
- Give agent mode separate eval profile.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** No broad agent framework beyond minimum required.

## Non-goals
- Optional; skip if no product use-case justifies complexity.

## Validation
- Agent-mode eval + safety tests

## Measurement
- Task success, latency/cost, tool error rate.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
