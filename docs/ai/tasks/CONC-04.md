# CONC-04 — Add bounded embedding micro-batching and ingestion fairness

**Phase:** Model serving performance  
**Priority:** P0  
**Branch:** `perf/embedding-microbatching`  
**Depends on:** `CONC-02`

## Goal

Use the SentenceTransformer model efficiently under concurrent query and ingestion load without running uncontrolled concurrent `encode()` calls.

## Audit evidence

- query RPC handler calls `encode_batch([text], batch_size=1)`;
- embedding RabbitMQ prefetch defaults to `1`;
- one Kafka embedding-job consumer processes each job and its batches sequentially;
- the model is process-local.

## Required architecture

Introduce one bounded inference scheduler around the model.

Inputs:
- live/query embeddings;
- memory query/passage embeddings;
- ingestion chunk batches.

Behavior:
- aggregate compatible requests for a very small configurable micro-batch window;
- configurable max batch size;
- configurable max queued requests/items;
- no unbounded waiting;
- preserve request result ordering;
- propagate individual request failures correctly;
- live/query traffic receives latency protection;
- ingestion receives guaranteed progress;
- one model instance owns inference.

Do not load multiple model copies merely to increase concurrency.

## Fairness

Define traffic classes at minimum:

- `live`
- `background/ingestion`
- `eval`

Use a bounded scheduling rule. A flood of ingestion jobs must not push live query p95 to the full ingestion batch duration.

## Pipeline

Keep existing large ingestion batches where efficient, but feed them through the same model ownership contract.

Evaluate Kafka `max_poll_records` only after the scheduler exists. Do not let consumer polling create more in-memory work than the scheduler can accept.

## Metrics

- scheduler queue depth;
- queue wait;
- actual batch size histogram;
- inference duration;
- items/sec;
- live vs background p95;
- rejected/timeout requests;
- model load count.

## Benchmark

Compare:
- single request latency;
- 4/8/16 concurrent query requests;
- ingestion-only throughput;
- mixed live query + ingestion;
- memory embedding + RAG embedding coexistence.

Quality gate: embedding vectors for a fixed input must remain equivalent within the model's deterministic/numerical tolerance.

## Tests

- result-to-request mapping across mixed batches;
- max batch bound;
- queue bound;
- live fairness;
- cancellation;
- malformed item affects only its defined failure scope;
- clean shutdown drains or fails queued work explicitly.
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
