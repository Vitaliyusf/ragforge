# RAG-05 — True dense+sparse hybrid retrieval

**Order:** 30  
**Phase:** 4 Retrieval V2  
**Priority:** P1  
**Branch:** `feat/hybrid-retrieval`  
**Depends on:** `CHUNK-01`, `VECTOR-01`

## Goal
Increase candidate recall for semantic and exact-term queries using Qdrant dense+sparse retrieval with measured fusion.

## Primary scope
- `Embedding sparse/query representation`
- `Vector/Qdrant named vectors/query API`
- `RAG retrieval client`
- `eval diagnostics`

## Required behavior
- Add sparse representation/search with Qdrant-supported approach.
- Retrieve bounded dense and sparse candidate pools.
- Fuse deterministically, starting with RRF.
- Apply identical tenant/review/retrieval filters on both arms.
- Expose effective retrieval config and per-arm diagnostics.
- Do not add Elasticsearch unless Qdrant demonstrably cannot meet a measured requirement.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Replace inactive hybrid flags with the one real implementation; no dense-v2 parallel path.

## Non-goals
- No reranker in this task.

## Validation
- Focused hybrid tests
- Vector/RAG suites
- Retrieval benchmark
- Smoke30 if promoted

## Measurement
- MRR, Recall@5/20, Hit@1, exact-term subset, latency.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
