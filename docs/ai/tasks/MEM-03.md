# MEM-03 — Create a memory quality golden set

**Order:** 38  
**Phase:** 5 Memory V2  
**Priority:** P1  
**Branch:** `feat/memory-quality-evals`  
**Depends on:** `MEM-01`, `MEM-02`

## Goal
Measure memory extraction, retrieval, staleness and false-memory behavior with deterministic labeled cases.

## Primary scope
- `Memory eval fixtures/runner`
- `existing eval infrastructure adapter`
- `metrics`

## Required behavior
- Cover episodic vs preference classification.
- Cover false-memory rejection, explicit preference update, expiry/staleness, paraphrase retrieval and conflict.
- Separate write-policy accuracy from retrieval ranking.
- Record model/prompt/index provenance.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Reuse current eval primitives instead of creating separate stores.

## Non-goals
- No second benchmark platform.

## Validation
- Memory eval suite

## Measurement
- Write precision/recall, retrieval precision/recall, false-memory rate, stale-memory rate.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
