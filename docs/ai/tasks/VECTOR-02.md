# VECTOR-02 — Optimize Qdrant hybrid search, delete and request patterns

**Order:** 33  
**Phase:** Retrieval V2 / performance  
**Priority:** P1  
**Branch:** `perf/qdrant-operations`  
**Depends on:** `CONC-00`, `CONC-02`

## Goal

Optimize measured Qdrant hot paths without changing retrieval semantics or weakening safety filters.

## Audit findings

### Hybrid search

`VectorService.search_chunks()` currently executes:

```text
dense Qdrant request
→ wait
→ sparse Qdrant request
→ wait
→ client-side RRF
```

The two retrieval arms are independent.

### Delete

`QdrantVectorStore.delete_chunks()` currently:

```text
scroll every matching point id
→ materialize all ids
→ delete ids
```

This scales poorly with large files/documents.

## Required work

### 1. Measure current operations

Capture p50/p95 and call count for:

- dense search;
- sparse search;
- hybrid search;
- upsert batches;
- delete by file/document;
- label lookup/scroll.

### 2. Hybrid request optimization

Prefer Qdrant server-side query composition/prefetch/fusion when the pinned server/client support it and it can reproduce the accepted RRF contract.

If server-side fusion cannot preserve the exact intended semantics, run dense+sparse concurrently with a bounded client executor instead.

Do not change RRF parameters merely for latency.

### 3. Filter delete

Use filter-native delete where possible rather than materializing every point ID.

If an exact deleted count is part of the business contract, obtain it with a bounded/count operation rather than retaining the full ID set in memory.

### 4. Payload indexes

Review actual production filters:
- tenant/user ownership;
- file/document;
- retrieval safety/review fields;
- label lookup fields.

Add/remove payload indexes only from measured query patterns.

### 5. Client lifecycle

Keep one Qdrant client per process. Do not construct a client per search.

## Acceptance

- tenant/user filters remain mandatory;
- dense/hybrid retrieval quality remains within accepted benchmark gates;
- hybrid network round trips reduced or overlapped;
- delete memory usage does not grow linearly with number of deleted point IDs;
- no stale-vector correctness regression.

## Measurement

Report:
- search p50/p95;
- hybrid p50/p95;
- delete p50/p95 at small/medium/large match counts;
- upsert throughput;
- Qdrant call count per operation;
- CPU/RAM;
- Hit/Recall/MRR/nDCG comparison.

Do not tune HNSW/quantization in this task unless a measured index-level bottleneck remains after request-path fixes.

## Execution rules

- Current source wins over this audit snapshot.
- Start with repository bootstrap / targeted code search before editing.
- Preserve unrelated dirty or untracked work.
- Never reset, stash, revert, or clean unrelated work.
- Do not commit or push unless explicitly requested.
- Do not repair `.venv`.
- Use canonical Python 3.12 tooling. If the host launcher is unsuitable, use the established isolated fallback:
  `uv run --isolated --python 3.12`
  with task-local state under `.agent-private/tooling/<TASK>/`.
- Do not add ad-hoc `--with <package>` dependencies merely to make validation pass.
- Test what changed; let CI test the repository.
- Run expensive/load benchmarks only when the task explicitly requires them.
- After the final production source edit, run final authoritative validation once, freeze source, update required handoff/decision records once, and stop.
- Do not weaken security, tenant isolation, durability, retrieval quality, memory correctness, or benchmark labels for performance.
