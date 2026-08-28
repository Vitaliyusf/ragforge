# TRACE-01 — Deep structured retrieval diagnostics

**Order:** 34  
**Phase:** 4 Retrieval V2  
**Priority:** P2  
**Branch:** `feat/rag-retrieval-diagnostics-v2`  
**Depends on:** `RAG-05`, `RAG-04`, `RAG-06`

## Goal
Make every retrieval stage explainable without exposing unbounded private content.

## Primary scope
- `retrieval_trace.py`
- `eval item diagnostics`
- `metrics/debug UI`

## Required behavior
- Capture bounded per-stage candidate IDs/ranks/scores/arm/lineage.
- Record drop/selection reason.
- Cover dense/sparse/fusion/rerank/neighbor/context stages.
- No unbounded raw passage text in normal traces.
- Version trace schema.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Extend existing trace model rather than adding parallel tracing.

## Non-goals
- No second diagnostics store.

## Validation
- Trace schema tests
- Eval/benchmark tests

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
