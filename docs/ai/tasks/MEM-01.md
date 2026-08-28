# MEM-01 — Use real neural embeddings for long-term memory

**Order:** 35  
**Phase:** 5 Memory V2  
**Priority:** P1  
**Branch:** `feat/neural-memory-embeddings`  
**Depends on:** `LLM-CTRL-01`, `VECTOR-01`

## Goal
Replace token-hash vector similarity with Embedding-service representations while keeping Mongo authoritative.

## Primary scope
- `Memory index client/service`
- `Embedding RPC`
- `memory schema/provenance`
- `Qdrant memory collection/tests`

## Required behavior
- Request memory/query embeddings through canonical Embedding service.
- Version model/dimension/representation.
- Keep lexical/keyword signal separately.
- Treat Qdrant as derived index and preserve Mongo fallback.
- Reindex existing memories safely.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Split index/vectorization concern out of memory_service.py and fix misleading semantic naming if needed.

## Non-goals
- No change to memory write policy in this task.

## Validation
- Memory+Embedding contract tests
- Memory retrieval benchmark

## Measurement
- Memory recall/precision, latency, index coverage.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
