# AGENT-03 — Memory agent evaluation harness

**Order:** 41  
**Phase:** 5 Memory V2  
**Priority:** P2  
**Branch:** `feat/memory-agent-evals`  
**Depends on:** `AGENT-02`, `MEM-03`

## Goal
Evaluate agent curation decisions against the memory golden set before expanding autonomy.

## Primary scope
- `agent eval adapter`
- `memory golden set`
- `benchmark reports`

## Required behavior
- Measure correct add/update/delete/no-op decisions.
- Measure destructive false-positive rate.
- Track tool steps/latency/token use.
- Use fixed config and deterministic evidence where possible.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Reuse Memory eval harness.

## Non-goals
- No production autonomy expansion.

## Validation
- Agent eval suite

## Measurement
- Decision accuracy, false destructive rate, steps, latency/tokens.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
