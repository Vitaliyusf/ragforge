# QUAL-01 — Consolidate claim coverage, citation edges and deterministic support metrics

**Order:** 43  
**Phase:** 6 Quality & Observability  
**Priority:** P2  
**Branch:** `feat/claim-quality-metrics-v2`  
**Depends on:** `VALIDATE-01`

## Goal
Strengthen claim-level quality measurement in one cohesive task instead of separate overlapping QUAL tasks.

## Primary scope
- `RAG eval claim/citation metrics`
- `golden-set schema`
- `EvalResults UI/tests`

## Required behavior
- Measure expected claim coverage.
- Represent claim↔citation support edges.
- Compute deterministic support/citation metrics where labels allow.
- Keep LLM-judge metrics separate.
- Version schema changes.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Absorb old QUAL-02/QUAL-03 and local eval metric cleanup.

## Non-goals
- No judge replacement.

## Validation
- Eval metric tests
- Frontend result tests

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
