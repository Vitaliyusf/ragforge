# CONC-00 — Establish repo-wide concurrency and performance baseline

**Phase:** Performance / concurrency foundation  
**Priority:** P0  
**Branch:** `perf/concurrency-baseline`  
**Depends on:** current main green

## Goal

Create the measurement contract used by every later concurrency task. Do not optimize production behavior in this task.

## Scope

Instrument and benchmark the critical request classes:

1. Gateway chat without RAG.
2. Gateway/RAG regular chat.
3. RAG extended retrieval.
4. embedding query RPC.
5. embedding ingestion job.
6. vector dense and hybrid search.
7. Memory read/write/retrieval.
8. file upload + ingestion handoff.
9. eval/benchmark background execution.

## Required metrics

Add/reuse low-cardinality metrics for:

- request/service in-flight count;
- queue wait before handler execution;
- handler/service duration;
- executor submitted/active/rejected/queued work where applicable;
- RabbitMQ RPC latency and timeout count;
- RabbitMQ consumer delivery/in-flight count;
- Kafka consumer lag and processing duration;
- event-loop lag for async services;
- background task count;
- downstream fallback/degraded-path count;
- embedding batch size and queue wait;
- reranker status (`success`, `busy`, `timeout`, `error`) and batch size;
- vLLM request concurrency, TTFT where available, output tokens/s where available;
- Mongo/Qdrant operation latency around identified hot paths.

Do not add tenant IDs, user IDs, request IDs, memory IDs, filenames, raw exceptions, or prompts to metric labels.

## Load profiles

Create a reproducible load harness or extend existing benchmark tooling.

At minimum support concurrency:

`1, 4, 8, 16, 32`

For GPU/model paths, stop increasing when the configured runtime clearly saturates; do not OOM hardware for a benchmark.

Each profile records:

- total requests/jobs;
- duration;
- achieved throughput;
- p50/p95/p99;
- success/error/timeout/fallback counts;
- CPU/RAM;
- broker lag/backlog when measurable;
- model/GPU evidence when measurable.

## Artifact

Emit machine-readable JSON under the existing benchmark artifact conventions with:

- Git SHA / source fingerprint;
- config snapshot;
- hardware/runtime;
- dataset/load profile;
- exact concurrency;
- metric summary;
- timestamp;
- known limitations.

## Acceptance

- baseline can run repeatedly without changing product state incorrectly;
- every later `CONC-*` task can compare against the same schema;
- no production concurrency behavior is changed;
- no performance claim is invented when the runtime needed to measure it is unavailable.
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
