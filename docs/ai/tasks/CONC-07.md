# CONC-07 — Make Memory hot paths indexed, bounded and pooled

**Phase:** Memory scalability  
**Priority:** P0  
**Branch:** `perf/memory-hotpaths`  
**Depends on:** `CONC-01`, `CONC-02`, `VECTOR-02`

## Goal

Remove corpus-wide Mongo scans, N+1 metadata writes and per-call Qdrant HTTP client construction from Memory V2 while preserving the authoritative Memory benchmark.

## Audit evidence

### Full scans

`_all_memory_documents()` loads both episodic and semantic collections for the current scope, and `_active_memory_documents()` filters owner/class/scope/status in Python.

This is used by retrieval and consolidation paths.

### Semantic comparison

`_comparable_memories()` loads all active memories to build `by_id` before a bounded vector search.

### Retrieval

`get_relevant_memories()` obtains all Mongo candidates and then scores them, even when Qdrant already returned bounded IDs.

### N+1 access touches

`_update_last_accessed()` locates and updates each returned memory individually.

### Qdrant HTTP

`MemoryVectorIndex._request()` creates a new `httpx.Client` for every call.

## Required work

### Query pushdown

Move canonical filters into Mongo:

- tenant/user scope;
- owner_id/owner_type;
- memory_class;
- lifecycle status;
- scope_key;
- valid_from/valid_to where queryable;
- declared identity keys.

Use narrow projections for ranking/identity queries.

### Vector-hit hydration

For semantic mode:

```text
Qdrant top-K ids
→ one bounded Mongo `$in` hydration
→ forced exact/fact/preference identities
→ deterministic merge
```

Do not load the owner's full memory corpus merely to hydrate top-K vector hits.

### Lexical fallback

Lexical fallback must also be bounded. Use an indexed/bounded candidate query or explicit configured cap.

Do not silently change the fallback into an unbounded scan.

### Bulk access update

Replace per-memory find/update with collection-aware bounded bulk/update-many operations.

### Qdrant client reuse

One pooled `httpx.Client`/equivalent per service lifetime with explicit close.

### Delete/reconciliation

Review `delete_memories_by_chat_id` and reconciliation loops for avoidable per-item database round trips. Batch only where lifecycle/tombstone semantics remain identical.

## Index review

Add only indexes required by the new queries. Prove query shape with explain/inspection where practical.

## Benchmark

Create synthetic owners at increasing memory counts, e.g.:

`10, 100, 1,000, 10,000`

Measure:
- get relevant memory p50/p95;
- write/consolidation p50/p95;
- Mongo documents examined / returned where available;
- Mongo call count;
- Qdrant/embedding call count;
- reconciliation throughput;
- RAM.

## Correctness gates

Run the 624-scenario deterministic Memory benchmark unchanged.

Must retain:
- tenant leakage = 0;
- user leakage = 0;
- resurrection count = 0;
- forbidden retrieval = 0;
- current/history correctness = 1.0 where currently guaranteed;
- deterministic projection equality.
## Validation — MINIMAL

Follow `CONC-VALIDATION-POLICY.md`.

For this task run only:

- the smallest focused regression test(s) that prove the changed behavior;
- Ruff on changed Python files;
- `git diff --check`.

Do **not** run a full service suite, repository suite, broad mypy, Docker rebuild, or load benchmark unless this task explicitly owns that measurement.

If the task includes a benchmark section, run only the smallest benchmark needed to prove this task's own performance claim. The full load campaign belongs to `CONC-99`.

## Execution rules

- Current source wins.
- Preserve unrelated dirty/untracked work.
- Never reset/stash/revert/clean.
- No commit/push unless explicitly requested.
- Do not repair `.venv`.
- Use isolated Python 3.12 fallback only if needed.
- Once the focused regression is green, STOP.
