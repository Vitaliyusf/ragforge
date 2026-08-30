# CONC-09 — Key and parallelize the Kafka ingestion pipeline while preserving per-document order

**Phase:** Distributed pipeline throughput  
**Priority:** P1  
**Branch:** `perf/kafka-keyed-parallelism`  
**Depends on:** `CONC-04`, `VECTOR-02`, `CONC-08`

## Goal

Increase ingestion throughput across independent documents without reordering dependent events for the same document/task.

## Audit evidence

- Files, Embedding and Vector DB each run a single Kafka consumer thread.
- Embedding job consumer polls `max_records=1`.
- producers do not consistently expose a partition key in the shared send contract.
- topic partitioning is not treated as an explicit ordering contract.

## Ordering contract

Choose and document the canonical ordering key for ingestion events.

Prefer:

```text
document_id / file_id
```

so all events for one document preserve Kafka partition order while different documents can run concurrently.

Task/retry semantics must remain idempotent.

## Required work

### Producer

- add optional message key support to the shared Kafka producer abstraction;
- use deterministic document key for ingestion pipeline events;
- preserve compatibility for non-keyed topics.

### Topics

Provision an explicit partition count suitable for local/demo load.

Do not hardcode a large production number. Make it configuration-owned.

### Consumers

- consumer group semantics must allow multiple workers/threads/processes to own different partitions;
- do not process two dependent events for the same document concurrently;
- raise `max_poll_records` only when downstream capacity can accept the batch;
- commit offsets only according to the existing successful-processing contract.

### Backpressure

Embedding scheduler and Vector DB capacity are the downstream bounds. Kafka consumers must not prefetch/poll an unbounded amount beyond them.

## Failure/rebalance tests

- two documents execute concurrently;
- one document's event sequence remains ordered;
- retries/redelivery do not duplicate durable state;
- rebalance during work is safe;
- failure before commit is replayable;
- poison message still reaches DLQ policy;
- lag metrics remain correct.

## Benchmark

Run multi-document ingestion at:

`1, 4, 8, 16` concurrent documents.

Report:
- docs/min;
- chunks/sec;
- per-stage p95;
- consumer lag;
- rebalance count;
- duplicate/idempotency failures;
- CPU/RAM;
- embedding/vector saturation.

Do not increase partitions/workers if the model or vector stage is already saturated.
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
