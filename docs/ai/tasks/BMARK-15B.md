# BMARK-15B — Honest latency semantics and LLM critical-path telemetry

**Branch:** `feat/benchmark-latency-telemetry`

## Goal

Make benchmark latency evidence truthful enough to optimize generation without confusing queue wait, execution time, and whole-phase wall clock.

Also add bounded, low-cardinality LLM telemetry by request type so we can identify whether time is spent in:

```text
answer_generation
answer_evaluation
content_risk_scan
query_rewrite
memory_extraction
```

## Problem

Current per-item benchmark latency starts before the eval semaphore is acquired.

Therefore:

```text
latency_ms
=
eval queue wait
+
actual item execution
```

This is useful as total elapsed time, but misleading if presented as retrieval/generation execution latency.

At the same time, the LLM service knows request type, usage and duration, but current benchmark evidence is not detailed enough to tune the critical path precisely.

## Required benchmark timing model

Persist/export separate measurements where applicable:

```text
queue_wait_ms
execution_ms
total_elapsed_ms
```

with:

```text
total_elapsed_ms ~= queue_wait_ms + execution_ms
```

Allow small clock/rounding differences.

Also expose:

```text
phase_started_at
phase_finished_at
phase_wall_clock_ms
```

### Definitions

`queue_wait_ms`
: time from item scheduling/start to semaphore acquisition.

`execution_ms`
: time inside the bounded execution slot.

`total_elapsed_ms`
: time from item scheduling/start until terminal per-item outcome.

`phase_wall_clock_ms`
: real wall-clock duration from phase start to phase terminal state.

Do not rename `total_elapsed_ms` to "request latency".

If backward compatibility requires keeping `latency_ms`, either:

- define it explicitly as `total_elapsed_ms`, or
- deprecate it in favor of the explicit fields.

Do not silently change its meaning without versioning/documentation.

## Required LLM telemetry

Use bounded `request_type` labels only.

At minimum provide evidence for:

```text
answer_generation
answer_evaluation
content_risk_scan
query_rewrite
memory_extraction
```

Track, where available:

```text
request count
error count
latency distribution
input tokens
output tokens
total tokens
finish reason
```

Use existing metrics infrastructure and traffic class separation.

### Strongly preferred

If feasible without invasive architecture changes, distinguish:

```text
LLM queue wait
model inference / provider call
total LLM request time
```

Do not invent these values if the current implementation cannot observe them cleanly.

## Prometheus / benchmark export

Benchmark snapshots should make it possible to answer:

```text
Which LLM action consumed the most wall time?
Which action had the worst p95?
Which action generated the most output tokens?
Did eval traffic queue behind live traffic?
```

Do not add high-cardinality labels such as:

```text
request_id
trace_id
conversation_id
item_id
prompt text
```

## Non-goals

Do not:

- tune RabbitMQ prefetch yet;
- tune vLLM `max-num-seqs` yet;
- change prompts/token budgets yet;
- remove evaluator/guardrail LLM calls;
- alter retrieval algorithms;
- run Full240.

## Required tests

At least:

1. queue wait is zero/near-zero when semaphore is immediately available.
2. second item waiting on semaphore records positive queue wait.
3. execution time starts after semaphore acquisition.
4. total elapsed reconciles with queue + execution.
5. timeout/error item still records timing.
6. phase wall clock is persisted and exported.
7. legacy rows without new timing fields remain readable.
8. LLM metrics use bounded request_type values only.
9. request counts increment by request type.
10. token usage skips missing provider usage rather than recording zero.
11. error metrics remain traffic-class separated.
12. benchmark/eval traffic does not pollute live-only aggregates unexpectedly.

## Validation

Run doctor once.

Focused RAG tests for eval timing.
Focused llm_agent tests for metrics.
Ruff changed files.

Because this changes benchmark timing plus LLM service metrics, run affected suites once near completion for:

```text
rag
llm_agent
```

No full local repo run.

## Manual acceptance

Run **Smoke30**.

Inspect diagnostic ZIP and Prometheus evidence.

Required:

```text
queue_wait_ms present
execution_ms present
total_elapsed_ms present
phase_wall_clock_ms present
LLM metrics grouped by request_type
```

Verify that large total elapsed values can now be explained as queue wait vs execution.

Do not run Full240.

## Final report

Return:

1. timing schema and definitions;
2. backward compatibility treatment of `latency_ms`;
3. LLM metrics added;
4. cardinality review;
5. focused/affected test counts;
6. Smoke30 evidence still required;
7. unresolved telemetry gaps.

Do not commit or push.
