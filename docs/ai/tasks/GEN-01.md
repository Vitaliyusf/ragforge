# GEN-01 — Remove avoidable LLM queue serialization

**Branch:** `perf/llm-queue-concurrency`

## Goal

Determine whether the LLM Agent RabbitMQ queue is unnecessarily serializing requests before they reach vLLM, and introduce the smallest safe configuration change that allows measured concurrency.

## Current evidence

The current architecture includes:

```text
EvalRunner concurrency > 1
LLM Agent max concurrent requests > 1
vLLM max_num_seqs > 1
```

while the LLM Agent RabbitMQ consumer currently uses a low prefetch value.

A low prefetch can prevent the downstream stack from using available inference concurrency.

This task must prove the bottleneck with measurements rather than assuming it.

## Required design

Do not globally change all llm_agent queues.

Introduce/use a dedicated bounded setting for the primary typed LLM execution queue, conceptually:

```text
LLM_REQUEST_PREFETCH
```

Keep summary/metadata/config/model-management queues on their current safe behavior unless a direct reason exists to change them.

Preferred initial supported values:

```text
1
2
4
```

Do not hardcode one "best" value in the task.

## Required observability

Before tuning, verify BMARK-15B telemetry can show:

```text
phase wall time
LLM request latency by action
errors/timeouts
token counts
```

Strongly preferred additional evidence:

```text
RabbitMQ consumer utilization / in-flight LLM requests
vLLM running/waiting requests if available
```

Do not add high-cardinality metrics.

## Experiment protocol

Use **Smoke30 Regular E2E only**.

Keep constant:

```text
same dataset
same Git SHA
same model
same GPU
same vLLM max_num_seqs
same eval concurrency
same token budgets
same retrieval config
```

Run:

```text
A: LLM_REQUEST_PREFETCH=1
B: LLM_REQUEST_PREFETCH=2
C: LLM_REQUEST_PREFETCH=4
```

Restart only services required for the configuration to take effect.

For every run capture:

```text
phase wall-clock
LLM p50/p95 by request_type
errors
timeouts
guardrail outcome counts
quality metrics
token usage
```

## Selection rule

Do not choose the largest prefetch automatically.

Choose the smallest value that gives most of the measurable wall-time benefit without:

```text
error increase
timeout increase
quality regression
guardrail regression
unacceptable live-traffic starvation
```

If prefetch does not materially improve wall time, preserve the current value and report the bottleneck hypothesis as disproven.

## Live traffic fairness

The system supports `traffic_class=live|eval`.

Do not optimize eval by making production/live traffic unusable.

If the queue architecture does not provide fairness, document the limitation.

Do not introduce a priority queue system in this task unless absolutely necessary for correctness.

## Non-goals

Do not:

- change `max_num_seqs`;
- change generation max tokens;
- change prompts;
- remove evaluator/guardrail calls;
- change retrieval;
- run Full240.

## Required tests

At least:

1. primary LLM queue can use its dedicated prefetch.
2. unrelated llm_agent queues retain their configured values.
3. invalid/non-positive prefetch is rejected or normalized safely.
4. consumer QoS receives the intended setting.
5. existing handler behavior is unchanged.
6. shutdown/reconnect behavior remains correct.
7. no test relies on nondeterministic real RabbitMQ timing.

## Validation

Doctor once.
Focused llm_agent config/messaging tests.
Ruff changed files.

Run llm_agent affected suite once near completion.

No full local repo test.

## Manual acceptance

Run the A/B/C Smoke30 Regular experiment.

Return the three diagnostic ZIPs or benchmark summaries plus configuration evidence.

Do not run Full240.

## Final report

Return:

1. bottleneck hypothesis;
2. implementation;
3. A/B/C measurements;
4. chosen prefetch or decision to keep current value;
5. quality/safety regression check;
6. focused/affected test counts.

Do not commit or push.
