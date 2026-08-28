# MEM-QUERY-01 — Move Memory filtering/scoring data access out of Python scans

**Order:** 36  
**Phase:** 5 Memory V2  
**Priority:** P1  
**Branch:** `perf/memory-query-scaling`  
**Depends on:** `MEM-01`

## Goal
Make Memory retrieval scale with indexed scoped Mongo queries and bulk updates rather than broad Python filtering.

## Primary scope
- `memory_service.py`
- `Mongo indexes/repository helpers`
- `Memory tests`

## Required behavior
- Push owner/type/class/archive filters into Mongo.
- Review/add compound indexes.
- Use bounded candidate depth.
- Bulk-update last_accessed_at.
- Keep deterministic ranking/diversification.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Extract repository/query concern from memory_service.py while touching it.

## Non-goals
- No ranking-policy redesign.

## Validation
- Memory suite
- Index/query tests
- Microbenchmark

## Measurement
- Docs scanned, latency, DB round trips.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
