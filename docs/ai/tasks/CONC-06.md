# CONC-06 — Parallelize independent Gateway/RAG DAG work with deterministic joins

**Phase:** Request-path latency  
**Priority:** P1  
**Branch:** `perf/rag-dag-parallelism`  
**Depends on:** `CONC-01`, `CONC-03`, `CONC-04`, `CONC-05`, `VECTOR-02`, `CONC-07`

## Goal

Reduce end-to-end chat latency by overlapping work that is semantically independent, while preserving checkpoints, stream order, failure attribution and deterministic state merges.

## Audit opportunities

### Gateway

`ChatService._prepare_context()` currently fetches:

```text
user insight
then
conversation history
```

These reads are independent.

### RAG regular path

After input guardrails, short-term context, memory retrieval and base chunk retrieval have no inherent write dependency before generation.

Evaluate whether they can fan out safely and join before reranking/generation.

### RAG extended path

Short-term context and deep memory retrieval can overlap. Query rewrite must still wait for both if it consumes both.

Pass-one subqueries already use bounded parallel retrieval; preserve that behavior.

### Persistence

`save_thread`, `save_turn`, `save_summary`, optional `save_answer_review`, then checkpoint are awaited serially.

Identify which writes are independent and can be overlapped. The durable checkpoint must not claim persistence completed before required writes succeed.

## Required design

- explicit fan-out/fan-in stages;
- bounded task count;
- `TaskGroup` or equivalent structured concurrency where appropriate;
- deterministic merge order independent of completion timing;
- cancellation of sibling work on fatal failure;
- explicit partial/fallback behavior for optional context reads;
- checkpoint semantics preserved;
- output stream order preserved.

Do not create background tasks for request-critical work without awaiting ownership.

## Tests

Use controlled delays to prove actual overlap:

- insight + history;
- short-term context + memory;
- regular retrieval branch where safe;
- persistence writes selected for overlap.

Also test:
- one branch fails;
- one branch times out;
- cancellation;
- deterministic merged state;
- checkpoint/resume parity;
- LangGraph and fallback-graph parity.

## Measurement

Before/after:
- context-preparation p95;
- regular chat TTFT/E2E;
- extended chat TTFT/E2E;
- downstream RPC count unchanged unless intentionally reduced;
- error/fallback rate;
- retrieval quality;
- persistence success rate.

Only accept parallelism that reduces measured wall time or removes head-of-line blocking.
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
