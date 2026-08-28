# VECTOR-02 — Optimize Qdrant operations after Retrieval V2 stabilizes

**Order:** 33  
**Phase:** 4 Retrieval V2  
**Priority:** P2  
**Branch:** `perf/qdrant-operations`  
**Depends on:** `RAG-06`

## Goal
Optimize Qdrant batching, filters, indexes and request patterns based on measured load after retrieval semantics stabilize.

## Primary scope
- `Qdrant client/collection config`
- `Vector service`
- `load benchmarks`

## Required behavior
- Profile search/upsert/delete latency and filter cost.
- Review payload indexes for real filters.
- Batch writes/deletes where useful.
- Tune HNSW/quantization only with quality+latency evidence.
- Avoid speculative low-level tuning.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Simplify VectorService transport/domain dispatch only if touched by measured bottleneck.

## Non-goals
- No quality algorithm changes.

## Validation
- Vector suite
- System/vector load benchmark

## Measurement
- Search p50/p95, upsert throughput, CPU/RAM, retrieval metrics.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
