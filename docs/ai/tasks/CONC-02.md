# CONC-02 — Replace implicit executor concurrency with bounded service backpressure

**Phase:** Performance / concurrency foundation  
**Priority:** P0  
**Branch:** `perf/bounded-executors`  
**Depends on:** `CONC-01`

## Goal

Make synchronous work offloaded from async services explicitly bounded, observable and gracefully shut down.

## Audit evidence

Request paths currently use `loop.run_in_executor(None, ...)` in:

- Files service;
- Vector DB service;
- LLM Agent handlers;
- Memory request handler;
- Embedding RPC handler.

The default executor is process-global and its capacity is not aligned with RabbitMQ prefetch or downstream limits.

## Required behavior

For every touched service:

- define an explicit service-owned concurrency budget;
- do not submit unbounded work to the default executor;
- bound both active work and queued submissions;
- expose in-flight/queue-wait/saturation metrics;
- preserve `contextvars` / request tracing;
- define overload behavior:
  - wait within a bounded deadline, or
  - fail fast with a typed overload response where the contract supports it;
- shut executors down cleanly in lifespan.

Prefer a small reusable shared adapter only if it removes duplicated semantics across services. Do not build a generic job framework.

## Budget rule

RabbitMQ `prefetch_count`, executor capacity, downstream concurrency and model/vector capacity must not contradict one another.

Document for each service:

```text
prefetch
executor workers
executor queue bound
downstream max concurrency
expected overload behavior
```

## Special rule: LLM Agent

Do not leave nested blocking pools where one handler thread waits on another provider thread. `CONC-03` owns the final LLM provider architecture; this task may introduce the bounded handler boundary needed for it but must not duplicate provider scheduling.

## Tests

- controlled slow handler proves event loop remains responsive;
- submissions never exceed configured bound;
- saturation is observable;
- cancellation/timeout does not leak capacity;
- shutdown does not hang;
- trace/auth context survives offload;
- per-service focused concurrency test with >capacity callers.

## Measurements

Report queue wait + handler p95 under 1x, 2x and 4x configured capacity.
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
