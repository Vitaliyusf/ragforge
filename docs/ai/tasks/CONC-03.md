# CONC-03 — Align LLM Agent concurrency with vLLM continuous batching

**Phase:** Model serving performance  
**Priority:** P0  
**Branch:** `perf/llm-concurrency-control`  
**Depends on:** `CONC-02`

## Goal

Remove avoidable client-side overhead and make one authoritative concurrency budget for RabbitMQ → LLM Agent → vLLM.

## Audit evidence

- `VLLMClient` owns `ThreadPoolExecutor(max_workers=max_concurrent_requests)`.
- Rabbit handlers are themselves offloaded to another executor.
- provider calls use `httpx.post/get/stream` convenience functions, so there is no long-lived HTTP connection pool.
- current Compose defaults disagree:
  - `LLM_REQUEST_PREFETCH=4`
  - `MAX_CONCURRENT_REQUESTS=10`
  - `VLLM_MAX_NUM_SEQS=4`.

## Required changes

### Provider transport

Use a long-lived HTTP client per process with explicit connection limits and keep-alive.

Choose sync or async deliberately:

- if keeping synchronous service methods, remove nested executor waiting and own exactly one blocking boundary;
- if moving provider calls async, migrate the touched call chain coherently rather than wrapping async in `asyncio.run`.

Preserve streaming, structured output, timeout and error contracts.

### Global inference budget

All LLM-producing queues share one bounded provider budget:

- answer generation;
- answer evaluation;
- risk scan;
- query rewrite;
- memory extraction/curation;
- summaries;
- metadata;
- generated questions.

Auxiliary queues must not collectively exceed the vLLM budget.

### QoS / fairness

Protect latency-sensitive live answer generation from background or auxiliary work.

Implement the smallest defensible policy, e.g. bounded class-specific semaphores plus a shared total budget.

Do not starve background jobs indefinitely.

### Timeout semantics

A client timeout must not leave an invisible provider thread occupying capacity indefinitely.

Report:
- queued;
- running;
- timed out;
- cancelled;
- provider completed after caller timeout if detectable.

## Tuning benchmark

Measure at vLLM request concurrency at least:

`1, 2, 4, 8`

and higher only if hardware remains healthy.

For each:
- RPS;
- TTFT p50/p95;
- end-to-end p50/p95;
- input/output tokens;
- output tokens/s;
- timeout/error rate;
- GPU memory/utilization if available.

Select config from measurements. Do not assume `10` is better than `4`.

## Acceptance

- one provider connection pool;
- one coherent provider concurrency budget;
- no nested executor waiting in the main request path;
- live traffic remains bounded during auxiliary load;
- chosen defaults are justified by benchmark evidence;
- existing structured-output and streaming tests remain green.
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
