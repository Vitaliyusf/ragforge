# Concurrency Baseline — the CONC-00 measurement contract

Every `CONC-*` task compares its numbers against this contract. It defines
what is measured, under which labels, at which concurrency points, and in
which artifact shape. Nothing here changes production concurrency behavior;
`CONC-00` is measurement only.

Read this alongside `docs/ai/BENCHMARKING.md`, which owns the reproducibility
and reporting rules this contract implements.

## The nine measured request classes

The `stage` label and the harness's scenario names use the same closed
vocabulary, declared once in `shared.metrics.CONCURRENCY_REQUEST_CLASSES`:

| Class | What it exercises | Transport |
|---|---|---|
| `gateway_chat_plain` | Gateway chat with RAG disabled | HTTP → RPC → vLLM |
| `gateway_chat_rag` | Regular RAG chat turn | HTTP |
| `rag_extended` | Extended retrieval: second pass, rerank, longer answer | HTTP |
| `embedding_query` | Single-query embedding | RabbitMQ RPC |
| `embedding_ingestion` | Batch embedding of an ingestion job | Kafka |
| `vector_search` | Dense and hybrid chunk search | HTTP → Qdrant |
| `memory_operation` | Long-term memory read/write/retrieval | HTTP |
| `file_ingestion` | Upload and the handoff into ingestion | HTTP → Kafka |
| `eval_background` | Eval/benchmark background execution | in-process task |

A task that adds a class must add it to that frozenset; the harness test
asserts the two lists stay identical, so they cannot drift apart.

## The metric contract

All metrics live in `backend/shared/metrics.py` under the
*Concurrency / saturation baseline* section. The service-side probes that
record them live in `backend/shared/concurrency_probe.py`.

**A declared metric is not an instrumented one.** `CONC-00` fixes the
vocabulary for the whole track, which means most of these names exist before
anything records them. Reading the table as "instrumented" would be the most
expensive mistake this document could invite: a later task would compare
against a series that was never populated and conclude the path was quiet.
So every metric carries its status, and the statuses mean:

- **WIRED** — a production path records it today, at a boundary `CONC-00`
  instrumented.
- **EXISTING / REUSED** — already recorded before `CONC-00`; the baseline
  adopts it rather than adding a parallel series.
- **DECLARED / NOT YET WIRED** — the metric and, where useful, an opt-in probe
  exist, but no production path calls it. The adopting task is named.
- **DEFERRED** — cannot be measured correctly until a later architectural
  change lands. Recording something in the meantime would mean inventing it.

### Wired in CONC-00

Instrumented at shared boundaries rather than in each service, so one edit
covers every service that already routes through them:

| Signal | Metric | Boundary |
|---|---|---|
| RabbitMQ consumer delivery / in-flight | `ragapp_rabbitmq_deliveries_total`, `ragapp_rabbitmq_inflight_deliveries` | `shared.rabbitmq_base.BaseRabbitMQConsumer._dispatch` |
| Kafka processing duration | `ragapp_kafka_message_processing_seconds` | `shared.kafka_base.BaseKafkaConsumer.consume` |
| RPC in-flight / timeouts | `ragapp_rpc_inflight`, `ragapp_rpc_timeouts_total` | `rag…conversation_backend_client._send_request`, beside the round-trip histogram it already owned |

### Existing / reused

| Signal | Metric | Where |
|---|---|---|
| RPC round-trip latency | `ragapp_rpc_roundtrip_seconds` | the same RAG dispatcher, pre-`CONC-00` |
| Kafka consumer lag | `ragapp_kafka_consumer_lag` | `BaseKafkaConsumer._record_lag`, from offsets the fetch already carried |

### Declared / not yet wired

The probe exists and is tested; no production path calls it yet.

| Signal | Metric | Adopting task |
|---|---|---|
| in-flight per request class | `ragapp_inflight_by_stage` | `CONC-01` (per-path adoption of `track_stage`) |
| queue wait before execution | `ragapp_queue_wait_seconds` | `CONC-01` |
| handler duration (non-HTTP entry points) | `ragapp_handler_duration_seconds` | `CONC-01` |
| executor ceiling / queue depth | `ragapp_executor_max_workers`, `ragapp_executor_queue_depth` | `CONC-02` (no service owns a snapshot call site yet) |
| executor submitted / rejected | `ragapp_executor_tasks_submitted_total`, `ragapp_executor_tasks_rejected_total` | `CONC-02` |
| event-loop lag | `ragapp_event_loop_lag_seconds` | `CONC-01` (the sampler owns a task; no service starts one) |
| background task count | `ragapp_background_tasks` | `CONC-04` — there is no task registry to count from today, and inventing one is a behavior change, not a measurement |
| fallback / degraded path | `ragapp_degraded_path_total` | `CONC-01`, `CONC-05` |
| embedding batch size | `ragapp_embedding_batch_size` | `CONC-06` |
| reranker status / batch size | `ragapp_reranker_status_total`, `ragapp_reranker_batch_size` | `CONC-05` |
| Mongo / Qdrant hot-path latency | `ragapp_mongo_operation_duration_seconds`, `ragapp_qdrant_operation_duration_seconds` | `CONC-07` |

### Deferred

| Signal | Metric | Why it cannot be measured yet |
|---|---|---|
| executor active workers | `ragapp_executor_active_workers` | `ThreadPoolExecutor` exposes no count of executing tasks. It spawns threads lazily and never retires them, so an idle pool still holds every thread it ever spawned and any arithmetic over `_threads` reports work that is not happening. `read_thread_pool` therefore returns `active=None` and the gauge is never set. `CONC-02` takes ownership of the executors and can then count submissions and completions exactly. |
| vLLM concurrency / TTFT / tokens per second | `ragapp_vllm_inflight_requests`, `ragapp_vllm_ttft_seconds`, `ragapp_vllm_output_tokens_per_second` | These are properties of the vLLM server's scheduler. Reading them needs the generation boundary `CONC-03` introduces; anything derived client-side today would measure the caller's queueing, not the model's. |

### Label rules

Labels are a closed vocabulary and are enforced by
`backend/shared/tests/test_concurrency_metrics.py`. Never add tenant ids, user
ids, request or trace ids, memory or document ids, filenames, prompts, queries
or raw exception text. `stage`, `reason`, `status`, `pool`, `kind`, `mode`,
`queue`, `collection` and `operation` all take fixed sets chosen by the code,
not by request data.

Two overlaps are deliberate and must not be collapsed:

- `ragapp_reranker_batch_size` is how many pairs went into one forward pass;
  `ragapp_reranker_candidate_count` is how many candidates the pipeline had.
  `CONC-05` changes the first, not the second.
- `ragapp_vllm_ttft_seconds` is the model's time to first token;
  `ragapp_rag_ttft_seconds` is the pipeline's. `CONC-03` needs to tell them
  apart.

## The load harness

`scripts/perf/` is host-side tooling. No service imports it.

```bash
py -3.12 scripts/perf/run_baseline.py \
    --gateway-url http://127.0.0.1:8000 \
    --username <user> --password <pass> \
    --requests 100 --warmup 10
```

- **Concurrency ladder:** `1, 4, 8, 16, 32` by default. A GPU-backed path can
  stop climbing through `run_ladder(stop_on_saturation=...)`; the ladder then
  ends short and says so rather than reporting a fabricated higher point.
- **Load model:** closed-loop. Exactly N concurrent callers, not N requests
  per second — an open-loop driver against a saturated stack would queue
  inside the harness and report its own backlog as the system's latency.
- **Warmup is discarded** but is driven at the profile's own concurrency, so
  pools are already the right size when measurement starts.
- **Writes are opt-in.** The default run drives read paths only, so the
  baseline is repeatable without changing product state. `--include-writes`
  enables `file_ingestion`, which creates documents.

### Outcome classification

Four outcomes, and the distinction between the first two is the point:

- `success` — a healthy answer.
- `fallback` — an answer the system had to degrade to produce (a RAG turn that
  came back with `use_rag: false`, extended retrieval with no sources). It
  counts toward throughput but never toward `success`.
- `timeout` — the per-call ceiling expired, or the service returned 408/504.
  Timeout latencies are excluded from the percentile summary, since a
  timeout's latency is the ceiling by construction.
- `error` — anything else.

## The artifact

JSON under `logs/perf/` (gitignored), one timestamped file per run,
`schema_version` bumped when the *shape* changes:

```
artifact, schema_version, created_at
source            git sha / branch / dirty / dirty-source fingerprint
config            allowlisted concurrency env only, never os.environ
hardware_runtime  platform, cpus, ram, whether resource sampling was possible
load              ladder, requests, warmup, timeout, load model, dataset
scenarios[]       name, status (measured|deferred), spec, profiles[], deferred_reason
limitations[]     everything the run could not support
```

Each profile carries nominal concurrency, request count, duration, achieved
throughput, the latency distribution, outcome counts, CPU/RAM and its own
limitations.

### Three honesty rules the tooling enforces

1. **A class that was not measured still appears, and says why.** Omission is
   what lets a later reader mistake "we never measured the reranker" for "the
   reranker was fine". `scenario_result` refuses an empty profile list that
   comes with no reason.
2. **A percentile the sample count cannot support is `null`.** Below 100
   samples the nearest-rank p99 is just the maximum, so it is withheld and the
   reason is written into the profile's limitations.
3. **An unmeasured resource is `null`, never `0`.** Without psutil the CPU and
   RAM fields are null and the run says so — a gauge reading zero because
   nothing looked is indistinguishable from a healthy zero, which is the
   reading an operator would trust. The same rule governs the metric statuses
   above and `executor_active_workers`: a value nobody measured is absent.
4. **A dirty tree is identified, not just confessed.** `dirty: true` alone
   tells a later reader their comparison is unsound without telling them
   which source produced the numbers, so a dirty run also carries
   `source_fingerprint_sha256` — the same content-addressed digest
   `scripts/build_rag_image.py` stamps into image provenance, reused rather
   than reinvented so an artifact and an image from one tree agree. It covers
   the tracked diff against `HEAD` plus every non-ignored untracked path and
   its content, so it moves when the source moves and holds still when it does
   not. It is a digest only: no diff, no file content, no path list and no
   environment travels with the artifact. A clean tree carries `null` there,
   because the SHA is already the identity and a hash of an empty diff would
   be a constant masquerading as a reading.

### The config allowlist is names the runtime reads

Every name in `perf.runtime.CONFIG_ALLOWLIST` is a variable current source
actually consults — a Compose `${...}` substitution, an `os.getenv` call, or a
pydantic settings field (readable uppercased: these configs set
`case_sensitive=False` with no `env_prefix`). A plausible name nothing reads is
worse than an absent one: it records `null` for a knob that is in force, and
two differently-configured runs then compare as identical.
`test_conc_baseline_harness.py` re-derives the readable names from
`docker-compose*.yml` and the service configs and fails when the list drifts.

Unset names are recorded as `null` rather than filled in from the Compose
default: the run either had the variable set or it did not.

## Running without a live stack

Docker being stopped degrades the artifact; it does not prevent one. A run
with no reachable services still fixes the schema, ladder, config allowlist
and build identity, and marks all nine classes `deferred` with reasons. Pass
`--require-live` to make a deferred class a non-zero exit instead — appropriate
for `CONC-99`, not for ordinary implementation tasks.

Under the default Compose topology only gateway (8000) and rag (8004) are
published to localhost, and the embedding query/ingestion paths are RabbitMQ
RPC and Kafka rather than HTTP at all. Those classes need a driver run from
inside the Compose network; `CONC-VALIDATION-POLICY.md` defers them to
CHECKPOINT B and the `CONC-99` campaign.

## Validation

```bash
py -3.12 scripts/ai/check.py lane perf-baseline   # harness, provenance, offline
py -3.12 scripts/ai/check.py lane shared          # metric contract and wiring
```

The metric contract and the two shared wiring boundaries are covered by
`backend/shared/tests/test_concurrency_metrics.py`; the harness, the config
allowlist and the source fingerprint by `tests/test_conc_baseline_harness.py`.
