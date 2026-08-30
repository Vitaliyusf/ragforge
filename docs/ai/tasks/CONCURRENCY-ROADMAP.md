# RagForge Concurrency / Parallelism / Performance Roadmap

**Audit date:** 2026-08-30  
**Scope:** repo-wide runtime hot paths across Gateway, RAG, LLM Agent, Embedding, Memory, Files, Vector DB, shared transports, frontend network behavior, Docker/process topology, and load evidence.

## Objective

Turn RagForge from a mostly correct single-process microservice stack into a measured, bounded, backpressured production system that can exploit concurrency without hiding races, multiplying downstream load, or degrading AI quality.

The target is not "make everything async." The target is:

```text
measure
→ remove transport/setup overhead
→ bound executor work
→ batch expensive model work
→ parallelize only independent DAG stages
→ eliminate O(N)/N+1 hot paths
→ preserve ordering where required
→ scale workers only after ownership is safe
→ prove p95/p99 and throughput gains under load
```

## Audit findings that drive this plan

| Finding | Current evidence | Owner |
|---|---|---|
| RabbitMQ RPC setup overhead | Gateway and RAG open a channel + exclusive reply queue for each request; RAG publish also opens a channel per event | `CONC-01` |
| Memory transport churn | Memory embedding opens a fresh robust RabbitMQ connection per embedding request | `CONC-01` |
| Memory Qdrant HTTP churn | `MemoryVectorIndex._request()` creates/closes `httpx.Client` per operation | `CONC-07` |
| Implicit thread-pool pressure | Files, Vector DB, LLM Agent, Memory use `run_in_executor(None, ...)` in request paths | `CONC-02` |
| Nested LLM executor | Rabbit handler occupies a default-executor thread while `VLLMClient` submits another thread and blocks on it | `CONC-03` |
| No vLLM HTTP connection pool | `httpx.post/get/stream` convenience functions are used per provider call | `CONC-03` |
| Concurrency budgets disagree | Compose: vLLM `max_num_seqs=4`, LLM prefetch=4, app `max_concurrent_requests=10` | `CONC-03` |
| Query embeddings are serialized tiny batches | Embedding RPC prefetch defaults to 1 and query handler calls `encode_batch([text], batch_size=1)` | `CONC-04` |
| Ingestion embedding batches are sequential | One Kafka job consumer processes batches serially | `CONC-04`, `CONC-10` |
| CrossEncoder degrades on concurrency | One executor worker; concurrent callers can receive `busy` and fall back to RRF | `CONC-05` |
| RAG/gateway independent work is still serial | Gateway fetches insight then history; RAG execution path serializes independent context loads | `CONC-06` |
| RAG persistence writes are individually awaited | thread/turn/summary/review/checkpoint writes serialize even when some are independent | `CONC-06` |
| Memory retrieval scans too much Mongo | canonical helper loads episodic + semantic collections then filters in Python | `CONC-07` |
| Memory access updates are N+1 | `_update_last_accessed` locates and updates each returned memory separately | `CONC-07` |
| Hybrid Qdrant search takes two sequential legs | dense query completes before sparse query; RRF happens client-side | `VECTOR-02` |
| Qdrant delete materializes IDs first | filter delete scrolls all matching point IDs before deleting | `VECTOR-02` |
| Upload path duplicates large payloads | Gateway buffers full file, joins bytes, base64 expands it, then sends it through RabbitMQ; Files decodes full content again | `CONC-08` |
| Kafka pipeline is effectively single-lane | single consumer threads; embedding job consumer explicitly polls `max_records=1` | `CONC-09` |
| All Python service images start one Uvicorn worker | every backend Dockerfile runs one `uvicorn app.main:app` process | `CONC-10` |
| Multi-worker scale is not universally safe yet | process-local Socket.IO state, eval tasks, consumers, model ownership and local semaphores exist | `CONC-10` |
| Frontend already has one good concurrency bound | Files bulk operations use `BULK_CONCURRENCY=4` | preserve in `CONC-11` |
| CI already parallelizes service tests | GitHub Actions service matrix exists | no new CI mega-task; optimize only if measured later |

`PERF-01` already introduced bounded async persistence offload for RAG. Do not reopen it.

## Execution order

```text
CONC-00  Baseline + concurrency observability
   ↓
CONC-01  Shared RabbitMQ RPC multiplexing / connection reuse
   ↓
CONC-02  Bounded executors + backpressure contract
   ↓
 ┌───────────────┬────────────────┬────────────────┐
 ↓               ↓                ↓                ↓
CONC-03         CONC-04          CONC-05          VECTOR-02
LLM             Embedding        Reranker         Qdrant
 └───────┬───────┴───────┬────────┘
         ↓               ↓
      CONC-07          CONC-08
      Memory           File I/O
         ↓               ↓
         └──────┬────────┘
                ↓
             CONC-06
             RAG/Gateway DAG parallelism
                ↓
             CONC-09
             Kafka keyed parallel pipeline
                ↓
             CONC-10
             Safe process/worker scale-out
                ↓
             CONC-11
             Frontend request/poll optimization
                ↓
             CONC-99
             Final load + portfolio evidence
```

Some service tasks may be developed in parallel after `CONC-02`, but merge/benchmark them in the order above so attribution remains clear.

## Validation strategy — intentionally sparse

Do **not** validate the whole repository on every task.

The track uses four milestone checkpoints plus one final authoritative run. See `CONC-VALIDATION-POLICY.md`.

Ordinary task:

```text
focused regression only
+ Ruff changed files
+ git diff --check
→ STOP
```

Full suites and expensive benchmarks are deferred to milestone checkpoints and `CONC-99`.

## Performance gates

Every optimization must report before/after where applicable:

- throughput / RPS or jobs/s
- p50 / p95 / p99 latency
- queue wait time
- in-flight count and saturation
- timeout/error/fallback rate
- CPU/RAM
- broker lag/backlog
- GPU utilization and tokens/s for model paths when available
- quality/correctness regression gates
- tenant/user leakage = 0
- deterministic benchmark contracts unchanged unless the task explicitly owns them

## What NOT to do

- Do not add Kubernetes yet.
- Do not blindly increase Uvicorn workers.
- Do not set RabbitMQ prefetch to a large number without a downstream concurrency budget.
- Do not create unbounded `asyncio.gather`.
- Do not create unbounded thread/process pools.
- Do not run multiple SentenceTransformer/CrossEncoder copies merely to claim parallelism.
- Do not increase vLLM concurrency past hardware capacity without TTFT/tok/s/load evidence.
- Do not sacrifice retrieval quality to reduce latency without explicit benchmark comparison.
- Do not add Redis/Celery/Temporal/MinIO unless a task proves the existing primitives cannot satisfy the requirement.

## Portfolio target

By the end of `CONC-99`, the repository should support defensible statements about:

- bounded concurrency and backpressure across service boundaries;
- multiplexed RPC transport and connection reuse;
- micro-batching for expensive embedding/reranking work;
- vLLM concurrency tuning against TTFT/throughput;
- deterministic parallel RAG DAG execution;
- keyed Kafka partitioning that preserves per-document order;
- indexed/bounded memory retrieval rather than corpus-wide scans;
- safe horizontal scale constraints and process ownership;
- measured before/after p95/p99 and throughput evidence.
