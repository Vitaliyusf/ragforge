# CHUNK-03 — Benchmark advanced chunking strategies

**Order:** 28  
**Phase:** 3 Document Representation V2  
**Priority:** P2  
**Branch:** `exp/advanced-chunking`  
**Depends on:** `CHUNK-01`, `CHUNK-02`

## Goal
Compare semantic splitting, sentence-window retrieval and late-chunking candidates without promoting any by intuition.

## Primary scope
- `experimental chunk transforms`
- `eval datasets`
- `benchmark manifests`

## Required behavior
- Run isolated candidates: semantic splitter, sentence-window, late chunking where model supports it.
- Hold parser/index/model fixed except the tested variable.
- Version each representation/index.
- Do not ship all strategies as permanent flags.
- Promote only measured winner; delete rejected experimental code/deps.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Experimental code stays outside canonical path and is deleted if rejected.

## Non-goals
- No agentic repair here.

## Validation
- Retrieval220/structured-doc benchmark
- Selected E2E quality benchmark

## Measurement
- MRR, Recall, nDCG, context precision, ingestion cost, index size.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
