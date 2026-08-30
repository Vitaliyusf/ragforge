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
record them live in `backend/shared/concurrency_probe.py` and are **opt-in**:
importing them starts no task and wires no handler, so a service that has not
adopted them yet behaves exactly as before.

| Signal | Metric |
|---|---|
| in-flight per request class | `ragapp_inflight_by_stage` |
| queue wait before execution | `ragapp_queue_wait_seconds` |
| handler duration (non-HTTP entry points) | `ragapp_handler_duration_seconds` |
| executor submitted / rejected | `ragapp_executor_tasks_{submitted,rejected}_total` |
| executor active / queued / ceiling | `ragapp_executor_{active_workers,queue_depth,max_workers}` |
| RPC latency / timeouts / in-flight | `ragapp_rpc_roundtrip_seconds`, `ragapp_rpc_timeouts_total`, `ragapp_rpc_inflight` |
| RabbitMQ consumer delivery / in-flight | `ragapp_rabbitmq_deliveries_total`, `ragapp_rabbitmq_inflight_deliveries` |
| Kafka lag / processing duration | `ragapp_kafka_consumer_lag`, `ragapp_kafka_message_processing_seconds` |
| event-loop lag | `ragapp_event_loop_lag_seconds` |
| background task count | `ragapp_background_tasks` |
| fallback / degraded path | `ragapp_degraded_path_total` |
| embedding batch size | `ragapp_embedding_batch_size` |
| reranker status / batch size | `ragapp_reranker_status_total`, `ragapp_reranker_batch_size` |
| vLLM concurrency / TTFT / tokens per second | `ragapp_vllm_inflight_requests`, `ragapp_vllm_ttft_seconds`, `ragapp_vllm_output_tokens_per_second` |
| Mongo / Qdrant hot-path latency | `ragapp_mongo_operation_duration_seconds`, `ragapp_qdrant_operation_duration_seconds` |

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
source            git sha / branch / dirty
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
   reading an operator would trust.

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
py -3.12 scripts/ai/check.py lane perf-baseline   # harness, offline
py -3.12 scripts/ai/check.py lane shared          # metric label contract
```
