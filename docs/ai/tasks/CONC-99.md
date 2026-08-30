# CONC-99 — Final concurrency/load benchmark and portfolio evidence

**Phase:** Performance closeout  
**Priority:** P0 closeout  
**Branch:** `perf/concurrency-final-evidence`  
**Depends on:** all accepted `CONC-*` tasks intended for this release

## Goal

Freeze concurrency configuration, run realistic load, identify the true saturation points, and produce defensible before/after evidence.

Do not use this task for broad new optimization. It is an evidence and finding task.

## Test profiles

At minimum:

### A. Chat / RAG
- regular RAG;
- extended RAG;
- direct LLM;
- concurrency 1/4/8/16 and higher only if stable.

### B. Mixed AI workload
Run a mix of:
- live chat;
- memory retrieval;
- embedding query;
- background eval/summary where supported.

Prove live-traffic QoS under background pressure.

### C. Ingestion
- multiple documents;
- different sizes/chunk counts;
- 1/4/8/16 concurrent docs as supported.

### D. Memory scale
- owner corpus sizes up to the scale supported by `CONC-07`.

### E. Overload
Intentionally exceed supported concurrency and prove:
- bounded queues;
- no unbounded memory growth;
- typed timeout/overload behavior;
- recovery after pressure is removed.

## Required metrics

Report before vs final:

- throughput;
- p50/p95/p99;
- TTFT;
- tokens/s;
- queue wait;
- broker lag;
- executor/scheduler saturation;
- CPU/RAM;
- GPU utilization/memory when available;
- timeout/error/fallback;
- reranker success/fallback;
- embedding batch-size distribution;
- Qdrant operation latency;
- Mongo examined/returned evidence where available.

## Correctness/quality gates

Run the authoritative relevant benchmarks unchanged.

At minimum:
- retrieval benchmark;
- Memory 624 deterministic benchmark;
- tenant/user leakage assertions;
- chat/stream safety tests;
- ingestion idempotency/order tests.

Any performance improvement that materially regresses quality must be reported, not hidden.

## Capacity statement

Produce a concise table:

```text
workload
supported concurrency
saturation signal
p95
throughput
primary bottleneck
recommended runtime setting
```

Separate:
- local demo hardware;
- production inference/runtime assumptions.

## Final artifacts

- machine-readable JSON;
- concise Markdown report;
- before/after charts only if repository benchmark conventions support them;
- exact config snapshot;
- Git/source fingerprint;
- limitations;
- strongest measured portfolio bullets.

## Stop rule

If the benchmark reveals a concrete blocker, create a narrowly scoped follow-up task. Do not fix it inside `CONC-99`.

After evidence is captured, freeze the release candidate.
## Validation authority

This task owns the **only full authoritative validation** for the concurrency track.

Run the complete affected backend/frontend suites, canonical mypy, Ruff, Docker/Compose validation, retrieval benchmark, Memory 624 benchmark, final load benchmark and `git diff --check` here — not in every earlier task.

## Execution rules

- Preserve unrelated work.
- Never reset/stash/revert/clean.
- No commit/push unless explicitly requested.
- Freeze source before the final benchmark.
- Fix only concrete failures found by this final evidence pass.
- STOP after final evidence.
