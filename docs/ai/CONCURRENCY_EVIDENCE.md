# Concurrency engineering evidence and portfolio closeout

**Track:** `CONC-00` through `CONC-10` (completed tasks only)

**Closeout:** `CONC-99`

**Source revision:** `1de81674bf13846c39b297df745c9f8c18cdb135`

**Evidence cut:** 2026-09-01

**Status:** ACCEPTED — core capacity and quality pass; final integrated soak deferred

This is the canonical public summary of the concurrency track. It consolidates
accepted measurements and contracts; it does not turn controlled results into
production claims. Unknown or lost measurements remain unknown.

## Evidence grades

| Grade | Meaning in this report |
| --- | --- |
| **A** | Real service, real broker, or real-corpus operational evidence. Scope is still limited to the named workload and runtime. |
| **B** | Controlled benchmark of production code, often with delayed substitutes around the unit under test. |
| **C** | Synthetic, stubbed, or model-specific benchmark; useful for a mechanism or tuning decision, not a production claim. |
| **D** | Historical claim whose supporting raw evidence is unavailable or was not independently verified during closeout. |

Grades apply to measurements, not to code quality. Deterministic contract tests
and operational verification are described separately where no performance
metric exists.

## Authoritative evidence inventory

| Task | Subsystem | Problem / baseline | Implementation | Accepted after measurement | Correctness guarantee | Test / evidence status | Important caveat | Source / evidence location |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `CONC-00` | Cross-service observability | No shared concurrency measurement contract; missing values could be confused with zero. | Defined nine request classes, low-cardinality saturation metrics, probes, and a closed-loop `1/4/8/16/32` harness with versioned JSON output. | No speedup claimed; this task is measurement-only. | Fallback is separate from success; unmeasured percentiles/resources are `null`; dirty trees get a source fingerprint. | Operational/test verification of schema, labels, probes, and offline harness. | Most metric declarations were adoption points for later tasks, not proof that every production path was already wired. | [`CONCURRENCY_BASELINE.md`](CONCURRENCY_BASELINE.md), `backend/shared/concurrency_probe.py`, `scripts/perf/` |
| `CONC-01` | RabbitMQ RPC | Gateway, RAG, and Memory paths created request-scoped channels, reply queues, or connections. | One process-owned bounded multiplexed client with reusable connection/channel/callback queue and correlation-ID future routing; migrated RPC, streaming, publish, and Memory bridges. | No accepted quantitative latency result retained. Transport resource churn was removed by construction. | Correlation isolation; timeout/cancellation cleanup; late-reply rejection; ordered stream routing; reconnect and deterministic shutdown. | Focused deterministic concurrency coverage and Ruff passed; task-time canonical pytest environment was blocked. | Do not claim a measured RPC latency or throughput improvement. | `backend/shared/rabbitmq_rpc.py`, `backend/shared/tests/test_multiplexed_rabbitmq_rpc.py`, durable contracts `CON-002` / `CON-003` |
| `CONC-02` | Synchronous RPC executors | Synchronous handlers relied on executor behavior without an owned queue/admission ceiling. | Service-owned bounded executors for Files, Vector DB, Embedding, Memory, and LLM Agent; explicit worker budgets, zero queued slots by default, typed admission timeout, saturation metrics, and drain-on-shutdown. | No accepted throughput delta retained. | Trusted context propagation; bounded submission; authenticated typed overload replies; consumers stop before pool drain. | Focused executor/transport coverage and Ruff passed; task-time canonical pytest environment was blocked. | This proves bounded overload behavior, not higher throughput. | [`CONCURRENCY_BUDGETS.md`](CONCURRENCY_BUDGETS.md), `backend/shared/bounded_executor.py`, durable contract `CON-010` |
| `CONC-03` | LLM Agent / vLLM | Nested provider execution, request-scoped HTTP calls, and conflicting defaults (`prefetch=4`, client=10, vLLM sequences=4). | One reusable bounded HTTP client and one fair process-wide provider budget; live/background admission aligned at four. | Fixed-shape probe at concurrency 4: **168.2959 output tokens/s**, TTFT p95 **0.1367 s**, E2E p95 **1.5232 s**, zero errors/timeouts. Concurrency 8: 194.9909 tokens/s, but TTFT p95 1.5217 s and E2E p95 2.6228 s. **Grade A** operational model-service probe. | Total provider work cannot exceed vLLM `max_num_seqs`; live work retains capacity; deterministic shutdown; typed overload. | Focused regressions, Ruff, canonical mypy, and fixed `1/2/4/8` probe passed. | Hardware/model/config specific; concurrency 4 is the measured interactive knee, not a universal vLLM setting or end-to-end chat result. | Durable decision `DEC-016`, `scripts/perf/vllm_concurrency_probe.py`, `backend/llm_agent/app/llm/provider_capacity.py` |
| `CONC-04` | Embedding model | Concurrent query/ingestion work could create uncontrolled `encode()` calls; queue priority alone could not protect live work once all workers were occupied. | One bounded cross-request scheduler with microbatching, result slicing, live capacity reservation, background progress, admission/timeouts, and one model load owner. Chosen physical workers: 3. | Mixed-load live p95 at live concurrency `1/4/8`: **699/786/1045 ms → 132/443/515 ms**; ingestion **185 → 213 items/s**; zero errors, overloads, or timeouts. **Grade C** controlled model/scheduler benchmark. | Bounded pending items and physical calls; deterministic result mapping; live reservation; background floor; cancellation and clean drain. | Scheduler/fairness regression coverage exists; accepted tuning evidence is retained in commit evidence. | Model/workload specific. An intermediate two-worker reservation protected latency but reduced ingestion to 77 items/s; the three-worker point was selected from measurement. | `backend/embedding/app/services/inference_scheduler.py`, `backend/embedding/app/tests/test_inference_scheduler.py`, commits `535b595` / `a2f65fc` |
| `CONC-05` | RAG CrossEncoder reranker | Single-flight scoring returned immediate `busy` under contention, changing learned ranking to RRF fallback as a function of load; candidate depth was 20. | One process-level bounded scheduler, two physical workers, live/background isolation, exact score-slice mapping, opportunistic batching, and an explicit `8/8/32/40` operating envelope (`candidate_k/max_batch/max_outstanding/max_pending`). | Stub probe: 100% learned-rerank success and zero `busy` at concurrency `1/2/4/8` (**Grade C**). Real-text c4: **20/20 success**, busy/timeout/fallback **0/0/0**, logical p95 ≈ **10.023 s**, physical predict p95 ≈ **5.339 s** (**Grade A**). Candidate pairs/request **20 → 8**, **60% fewer** (**Grade A** configuration/workload result). | No fallback merely because a worker is occupied; bounded admission; exact request/result mapping; live capacity reservation; cancellation recovery; deterministic ranking. | Focused scheduler coverage passed. Retrieval220 run `e6182717-afa8-4a58-bfca-a34a65a3e926`: 220/220 evaluated, stale/unscorable/failed `0/0/0`, Hit@1 `0.9863636364`, Recall@5 `0.9886363636`, MRR `0.9878787879`, nDCG@10 `0.9871990405` (**Grade A**, real corpus). | Establishes reranker capacity plus retrieval quality, not final integrated soak or production end-to-end latency. Raw real-text/log artifact is not tracked in the public tree; accepted closeout values are frozen here. | Durable decision `DEC-017`, `backend/rag/app/services/rerank_scheduler.py`, `scripts/perf/reranker_concurrency_probe.py`, commits `24d6243` / `4768416` |
| `CONC-06` | Gateway request DAG | Insight and conversation-history reads were awaited serially even though independent. | A fixed `TaskGroup` of two context reads with an owned join. | p50 **108.53 → 46.92 ms**; p95 **110.03 → 47.54 ms**; approximately **56.8% lower** context-preparation latency. **Grade B** controlled production-code microbenchmark with delayed RPC substitutes. | Deterministic tuple assembly; existing optional fallback semantics; sibling cancellation and cleanup. | Four focused Gateway tests, Ruff, canonical mypy, and diff checks passed. | Not production end-to-end RAG latency, TTFT, or an HTTP load result. | `backend/gateway/app/services/chat_service.py`, `backend/gateway/app/tests/routes/test_chat.py`, commit `eca8598` |
| `CONC-09` | Kafka ingestion | One consumer thread per stage and unkeyed publishing serialized independent documents without making same-document ordering an explicit contract. | Optional producer keys, deterministic document/file keys, and bounded partition-worker pools for Files, Embedding, and Vector DB; local/demo default: four partitions/workers. | Controlled many-key **64.35 → 193.38 msg/s**: about **3.0×**, **+200.5%**, **66.7% less wall time**. Hot-key **65.17 → 79.52 msg/s**, **+22.0%**. **Grade B**. Live Kafka: 4 partitions/workers, same key on one partition, cross-partition overlap, ordering violations/errors/final lag **0/0/0**. **Grade A** broker contract verification. | Same-key partition order; bounded workers; existing commit-on-success behavior; no custom offset coordinator; clean shutdown. | Controlled benchmark and live broker contract passed; focused static checks passed. | Existing application topics were observed with one partition. Production requires explicit provisioning/migration. The 3× benchmark is not a production Kafka throughput result. | `backend/shared/kafka_base.py`, `backend/shared/kafka_workers.py`, `scripts/benchmarks/conc09_kafka_keyed_parallelism.py`, commits `f3fb61a` / `f50b40f` |
| `CONC-10` | Memory horizontal scale | One Memory consumer replica despite externally owned durable state and no local model. | Configurable Compose replicas using RabbitMQ competing consumers; default remains one; per-replica QoS/executor bounds remain intact. | Bounded read-only `get_chats`, 200 RPCs at c32: **334.394 → 839.850 req/s**; p50 **299.632 → 131.281 ms**; p95 **562.932 → 232.315 ms**; zero errors; deliveries **109/111**. Failure probe after stopping one replica: **2000/2000** successful, queue ready/unacknowledged **0/0**. RSS total ≈ **57.6 → 115.1 MiB**. **Grade A** real service/broker operational evidence. | MongoDB/Qdrant own correctness state; RabbitMQ safely redistributes unacknowledged work; bounded admission remains per replica. | Compose scale resolution, comparison, delivery split, and failure-continuity probe passed. | Evidence is only for 1-vs-2 replicas on bounded read-only `get_chats`; it does not establish generic, linear, superlinear, write-path, or unlimited-replica scaling. | Durable capability `CAP-018`, `.agent-private/HANDOFF.md`, commit `67f14ae` |

## Consolidated portfolio metrics

| Area | Before | After | Result | Evidence type / grade |
| --- | ---: | ---: | --- | --- |
| vLLM interactive operating point | c8: TTFT p95 1.5217 s; E2E p95 2.6228 s | c4: 168.2959 output tokens/s; TTFT p95 0.1367 s; E2E p95 1.5232 s | Four selected as the latency/throughput knee; 0 errors/timeouts | Operational model-service probe — **A** |
| Embedding mixed load, live c1 p95 | 699 ms | 132 ms | 81.1% lower | Controlled model/scheduler — **C** |
| Embedding mixed load, live c4 p95 | 786 ms | 443 ms | 43.6% lower | Controlled model/scheduler — **C** |
| Embedding mixed load, live c8 p95 | 1045 ms | 515 ms | 50.7% lower | Controlled model/scheduler — **C** |
| Embedding ingestion | 185 items/s | 213 items/s | 15.1% higher | Controlled model/scheduler — **C** |
| CrossEncoder candidate pairs/request | 20 | 8 | 60% fewer pairs | Accepted real-text/config workload — **A** |
| CrossEncoder real-text c4 | Immediate-busy architecture under contention | 20/20 success; busy/timeout/fallback 0/0/0; logical p95 ≈10.023 s; physical predict p95 ≈5.339 s | Capacity envelope works without quality fallback | Real service/text operational — **A** |
| Retrieval220 quality | Not a before/after speed claim | Hit@1 0.9863636364; Recall@5 0.9886363636; MRR 0.9878787879; nDCG@10 0.9871990405 | 220/220 evaluated; 0 stale/unscorable/failed | Real-corpus deterministic evaluation — **A** |
| Gateway context preparation p50 | 108.53 ms | 46.92 ms | 56.8% lower | Controlled production-code microbenchmark — **B** |
| Gateway context preparation p95 | 110.03 ms | 47.54 ms | 56.8% lower | Controlled production-code microbenchmark — **B** |
| Kafka many-key throughput | 64.35 msg/s | 193.38 msg/s | ~3.0× / +200.5%; 66.7% less wall time | Controlled benchmark — **B** |
| Kafka hot-key throughput | 65.17 msg/s | 79.52 msg/s | +22.0% | Controlled benchmark — **B** |
| Kafka ordering contract | Single serial worker | 4 partitions/workers; 0 ordering violations, processing errors, or final lag | Same-key order with cross-partition overlap | Live broker verification — **A** |
| Memory read throughput | 334.394 req/s (1 replica) | 839.850 req/s (2 replicas) | Workload-specific 1-vs-2 gain; 0 errors | Real service/broker — **A** |
| Memory read latency p50 / p95 | 299.632 / 562.932 ms | 131.281 / 232.315 ms | Lower latency for the bounded read workload | Real service/broker — **A** |
| Memory replica failure | Not applicable | 2000/2000 successful after one replica stopped; queue 0/0 | Competing-consumer continuity demonstrated | Real service/broker — **A** |
| Memory RSS total | ~57.6 MiB | ~115.1 MiB | ~57.5 MiB added for the second replica | Operational observation — **A** |
| Memory deterministic quality | Historical accepted run | 624 scenarios: EN 208, HE 208, mixed 208; nDCG 0.9903744119787171 | Broader correctness retained; not caused by concurrency work | Deterministic synthetic evaluation — **C** |

The Memory 624 result is deliberately contextual evidence only. Its retained
artifact identifies a synthetic Unicode bag-of-words measurement stub and does
not measure production multilingual E5 quality.

## Concurrency architecture

### I/O concurrency

- Async service boundaries keep network waits off request executors where the
  call chain supports async I/O.
- Gateway context preparation owns exactly two independent reads in an
  `asyncio.TaskGroup`, then joins them in deterministic field order.
- RAG/eval fan-out is bounded at its owning stage; request-critical work is
  awaited rather than detached into unowned background tasks.
- RabbitMQ RPC uses process-owned multiplexed transports and correlation
  registries instead of a connection/channel/reply queue per request.

### CPU and model work

- CrossEncoder work enters one bounded scheduler with two physical workers,
  pair-count admission, live/background isolation, and exact score slicing.
- Embedding work enters one bounded scheduler around one model instance;
  compatible requests may microbatch, but pending items and physical calls are
  capped and live capacity is reserved.
- LLM Agent has one fair provider budget aligned with vLLM's four-sequence
  scheduler and one reusable HTTP pool. There is no nested provider executor.
- Model work is never expanded through unbounded task creation.

### Queue backpressure

- RabbitMQ QoS/prefetch and per-service bounded executors define delivery and
  synchronous-handler ceilings; overload is typed and observable.
- Kafka concurrency is partition-owned and worker-count bounded. Polling does
  not create an independent unbounded work coordinator.
- Reranker admission is explicit: candidate K 8, max batch pairs 8, max
  outstanding pairs 32, max pending pairs 40, workers 2.
- Queue wait, rejection, timeout, fallback, in-flight work, and broker lag use
  low-cardinality metrics defined by the baseline contract.

### Ordering

- Kafka's document/file key maps every dependent event for one document to one
  partition, preserving broker order while independent partitions overlap.
- Reranker and embedding batches keep exact offsets back to the original
  request; completion timing cannot reorder a caller's result.
- Gateway assembly order is fixed independently of which context read finishes
  first.
- Kafka retains its existing success/commit contract; there is no custom unsafe
  offset coordinator.

### Horizontal scale and deliberate non-scale decisions

- Memory is the demonstrated horizontal-scale target: correctness state lives
  in MongoDB/Qdrant, model work is external RPC, and RabbitMQ provides competing
  consumers. Scale remains opt-in because per-replica executor/prefetch capacity
  and downstream load still multiply.
- RAG does **not** scale transparently by default. It owns Socket.IO connection
  state, request/task ownership, eval/background tasks, local schedulers, and a
  process-local CrossEncoder. Replica scale needs a shared Socket.IO manager or
  routing contract plus explicit task/consumer ownership.
- LLM Agent/vLLM does **not** multiply by ordinary web-worker count. The vLLM
  server owns the real model capacity; extra consumers must not multiply the
  four-slot global inference budget or duplicate process-local scheduling.
- Gateway HTTP work is comparatively stateless, but the token-bucket rate
  limiter is process-local. Transparent replicas require shared/distributed
  rate-limit state or an explicitly per-replica policy.
- Embedding is model-heavy. Extra processes duplicate model RAM/device cost and
  consumer capacity; scale by measured device/model ownership, not generic
  Uvicorn worker count.

These constraints are capacity-ownership decisions, not missing optimization.

## Resume-safe bullet candidates

- Reduced CrossEncoder candidate work by **60% (20 to 8 pairs/request)** while
  retaining **0.9872 nDCG@10** across a 220-query corpus evaluation, using
  bounded pair admission and measured two-worker model concurrency.
- Replaced load-dependent CrossEncoder `busy` fallback with a bounded scheduler;
  a real-text concurrency-4 run completed **20/20** requests with zero busy,
  timeout, or fallback outcomes.
- Implemented document-keyed Kafka partition concurrency with bounded workers,
  preserving per-document order with **zero ordering violations, processing
  errors, and final lag** in a live four-partition broker verification.
- Enabled RabbitMQ competing-consumer scaleout for an externally stateful Memory
  service; two replicas raised bounded read throughput from **334.394 to
  839.850 req/s** with zero errors and **2000/2000** successful requests after
  one replica was stopped.
- Cut controlled Gateway context-preparation p95 from **110.03 to 47.54 ms
  (56.8%)** by joining two independent RPC reads with structured concurrency
  while preserving deterministic fallback and cancellation semantics.
- Built a live-protected embedding microbatch scheduler that reduced mixed-load
  query p95 from **699/786/1045 ms to 132/443/515 ms** at live concurrency
  1/4/8 while increasing measured ingestion throughput from 185 to 213 items/s.

## Interview stories

### 1. Reranker capacity versus retrieval quality

- **Problem:** The second concurrent request could receive `busy`, silently replacing learned ranking with RRF and making quality depend on traffic.
- **Constraint:** One pinned CPU CrossEncoder, bounded latency and memory, live traffic sharing capacity with eval work, and no second model copy.
- **Decision:** Centralize ownership in a pair-count scheduler with two workers, live/background isolation, exact result offsets, and an `8/8/32/40` admission envelope. Use opportunistic batching with no artificial collection delay.
- **Tradeoff:** The real model remains slow (logical p95 ≈10.023 s); the design makes capacity explicit and preserves quality rather than disguising the cost with fallback or a longer timeout.
- **Measurement:** Real-text c4 completed 20/20 with zero busy/timeouts/fallbacks; candidate work fell 60%. Retrieval220 delivered nDCG@10 0.9871990405 with all 220 queries scorable and successful.
- **Failure mode considered:** Queue overload, cancellation, inference timeout, model error, and eval traffic occupying all physical workers.
- **Result:** Core capacity plus retrieval quality passed; final integrated soak did not run.
- **Next in production:** Add model cold-start warmup/readiness and run a full mixed-stack soak with queue-wait, CPU/RAM, fallback, and tail-latency capture.

### 2. Kafka keyed ordering and concurrency

- **Problem:** Single consumers serialized independent documents, while missing keys left the ordering contract implicit.
- **Constraint:** Same-document events must stay ordered and replayable; offset commits, DLQ behavior, and downstream embedding/vector bounds must survive.
- **Decision:** Key by document/file ID and let Kafka partitions own ordering; use bounded workers assigned by the consumer group rather than a custom offset coordinator.
- **Tradeoff:** Hot keys cannot use all partitions, and deployed topics must actually be partitioned before worker concurrency can help.
- **Measurement:** Controlled many-key throughput rose 64.35→193.38 msg/s; hot-key throughput rose 65.17→79.52. A live four-partition run showed overlap, same-key affinity, zero ordering violations/errors/final lag, and clean exit.
- **Failure mode considered:** Same-key reordering, failure before commit, redelivery, rebalance, poison messages, and shutdown with in-flight work.
- **Result:** The concurrency/ordering contract is broker-proven; the 3× number remains a controlled result, not a production throughput claim.
- **Next in production:** Provision or migrate application topics explicitly, then measure end-to-end document throughput and downstream saturation.

### 3. Memory horizontal scaling

- **Problem:** Memory ran one consumer even though durable correctness state was external and the service loaded no model.
- **Constraint:** Scaling must not duplicate ownership, violate tenant/user isolation, lose unacknowledged work, or imply downstream-bound writes scale.
- **Decision:** Make Compose replicas configurable and use RabbitMQ competing consumers while keeping bounded prefetch and executors per replica.
- **Tradeoff:** A second replica approximately doubles service RSS and multiplies potential downstream pressure; default remains one.
- **Measurement:** On bounded read-only `get_chats`, 1→2 replicas moved 334.394→839.850 req/s, p95 562.932→232.315 ms, zero errors, and a 109/111 delivery split. After stopping one replica, 2000/2000 requests succeeded and the queue drained to ready/unacknowledged 0/0.
- **Failure mode considered:** Consumer death with delivered work, queue drain, uneven delivery, duplicate state ownership, and resource multiplication.
- **Result:** Safe 1-vs-2 read-path scaleout and failure continuity are measured.
- **Next in production:** Test semantic write/retrieval mixes, downstream limits, rolling failure, and more than two replicas before widening the claim.

### 4. Gateway structured concurrency

- **Problem:** Two independent context RPC reads ran serially on every chat preparation path.
- **Constraint:** Output order, optional fallback behavior, cancellation cleanup, and request ownership could not change.
- **Decision:** Use one fixed `TaskGroup` containing exactly the insight and history reads, then assemble their results deterministically.
- **Tradeoff:** Both downstream calls now overlap, so instantaneous downstream concurrency rises by one per active preparation; task count remains fixed.
- **Measurement:** With controlled delayed RPC substitutes, p50 fell 108.53→46.92 ms and p95 110.03→47.54 ms, about 56.8% lower.
- **Failure mode considered:** One branch failing or timing out, sibling cancellation, fallback of optional data, and nondeterministic completion.
- **Result:** A bounded structured join removed serial wait without changing the response contract.
- **Next in production:** Capture this stage inside a representative chat soak; do not extrapolate the microbenchmark to end-to-end RAG latency.

## Deferred / not blocking portfolio

- RAG CrossEncoder cold-start warmup and readiness.
- Checkpoint B final integrated soak.
- Historical structured-output event whose supporting logs were lost.
- Kafka production-topic partition provisioning/migration.
- Distributed Gateway rate limiting before transparent horizontal scale.
- RAG Socket.IO/WebSocket and background-task ownership before replica scaleout.
- `CONC-11` frontend network control; deferred for low portfolio return.

## Claims deliberately rejected

- “Production Kafka throughput improved 3×.” The 3× result is controlled; the live broker run proves ordering/concurrency, and production topics were still observed at one partition.
- “Memory scales horizontally by 2.5×” or “superlinearly.” Only a bounded read-only 1-vs-2 comparison is established.
- “Gateway end-to-end RAG latency improved 56.8%.” Only the context-preparation unit was measured with delayed RPC substitutes.
- “Concurrency improved Memory nDCG.” The 624-scenario result predates and is independent of the scaleout work.
- “The full stack is soak-proven.” The integrated soak was explicitly deferred.
- “All cold starts are production-ready.” CrossEncoder warmup/readiness remains follow-up work.
- Any numeric RPC multiplexing or bounded-executor speedup. No accepted quantitative result was retained for `CONC-01` or `CONC-02`.

## Project headline

**Production AI systems engineer: built bounded RAG/LLM concurrency across
RabbitMQ, Kafka, CPU/GPU model schedulers, and structured async request paths,
with measured capacity, retrieval-quality, ordering, and failure-continuity
evidence—and explicit limits on what the benchmarks prove.**

## Decision

**CONC-99 ACCEPT**
