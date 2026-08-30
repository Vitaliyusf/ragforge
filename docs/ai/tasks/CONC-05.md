# CONC-05 — Replace CrossEncoder `busy` fallback with a bounded reranker scheduler

**Phase:** Retrieval performance  
**Priority:** P0  
**Branch:** `perf/reranker-scheduler`  
**Depends on:** `CONC-02`

## Goal

Prevent concurrent traffic from silently degrading learned reranking quality simply because the single CrossEncoder worker is occupied.

## Audit evidence

`CrossEncoderReranker` currently:

- owns `ThreadPoolExecutor(max_workers=1)`;
- tracks one `_inflight` future;
- returns status `busy` and preserves RRF order when another request arrives.

This turns load into a retrieval-quality change.

## Required behavior

Build a bounded scheduler for reranking:

- one model instance;
- bounded waiting queue;
- explicit queue timeout / overload policy;
- no immediate quality fallback solely because one request is already running;
- optional micro-batching across concurrent rerank requests if measurement proves useful;
- deterministic mapping of scores back to each query/candidate list;
- cancellation-safe cleanup;
- clean shutdown.

If CPU-only CrossEncoder cannot meet the live latency budget, record that fact. Do not hide it by increasing timeout until the request "passes".

## Quality rule

Track separately:

- `success`;
- `queue_timeout`;
- `inference_timeout`;
- `overload`;
- `model_error`;
- deliberate RRF fallback.

A concurrency overload must be visible in benchmark output.

## Benchmark

At candidate K values used by production, measure:

- 1/2/4/8 concurrent rerank requests;
- queue wait p95;
- inference p95;
- total p95;
- reranker success rate;
- RRF fallback rate;
- CPU/RAM;
- retrieval quality metrics.

Compare at least:
- current CPU CrossEncoder runtime;
- improved scheduler on the same model/runtime.

Do not change model/revision in this task unless the existing runtime is proven operationally unusable and a separate measured decision is recorded.

## Acceptance

- concurrency no longer produces arbitrary `busy` fallbacks within the supported queue budget;
- quality metrics remain stable;
- overload is bounded and observable;
- eval concurrency does not silently bypass reranking.
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
