# RAG-06 — Neighbor expansion and evidence diversity policy

**Order:** 32  
**Phase:** 4 Retrieval V2  
**Priority:** P2  
**Branch:** `feat/retrieval-context-expansion`  
**Depends on:** `RAG-04`, `CHUNK-01`, `RAG-03`

## Goal
Use structured adjacency and diversity to build coherent evidence spans without wasting context.

## Primary scope
- `RAG post-rerank/context policy`
- `chunk metadata lookup`
- `context assembler/tests`

## Required behavior
- Expand neighbors only within same document/version and compatible section.
- Merge contiguous spans deterministically.
- Stay inside evidence token budget.
- Apply MMR/diversity only after relevance constraints.
- Preserve citation mapping to source chunks/spans.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Extend the RAG-03 assembler/policy; do not create a second context pipeline.

## Non-goals
- No new retrieval backend.

## Validation
- Focused adjacency/diversity tests
- Retrieval + E2E benchmark

## Measurement
- Context tokens, source diversity, answer/citation quality, latency.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
