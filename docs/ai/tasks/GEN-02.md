# GEN-02 — Tune vLLM request concurrency with controlled A/B measurements

**Branch:** `perf/vllm-concurrency`

## Goal

Tune vLLM scheduling concurrency only after GEN-01 has removed any upstream queue serialization.

## Dependency

Complete GEN-01 first.

Use the selected LLM queue prefetch value from GEN-01.

## Current tunable

The vLLM service exposes:

```text
--max-num-seqs
--gpu-memory-utilization
--max-model-len
```

This task is primarily about `max-num-seqs`.

Do not tune all three simultaneously.

## Experiment protocol

Use **Smoke30 Regular E2E only**.

Keep constant:

```text
same Git SHA
same dataset
same GPU
same model
same quantization
same max_model_len
same gpu_memory_utilization
same queue prefetch
same eval concurrency
same token budgets
```

Test a small sweep suitable for the current GPU, for example:

```text
max_num_seqs = 2
max_num_seqs = 3
max_num_seqs = 4
```

If the active GPU cannot safely support a value, stop that candidate and record the failure.

## Required measurements

For each candidate capture:

```text
Regular E2E phase wall-clock
LLM request p50/p95
TTFT if available
input/output tokens
timeouts
errors
vLLM OOM/restart events
GPU memory utilization if available
running/waiting request evidence if available
quality metrics
guardrail counts
```

## Decision rule

Choose the candidate that gives the best useful throughput/wall-time tradeoff without:

```text
OOM
service restarts
timeout regression
large TTFT regression
quality regression
safety regression
```

Do not choose the highest concurrency merely because it is higher.

If `2` is already optimal, keep it.

## Optional follow-up

Only if `max_num_seqs` is clearly limited by unused memory and the evidence supports it, a later task may test `gpu-memory-utilization`.

Do not combine that experiment into this task.

## Non-goals

Do not:

- change RabbitMQ prefetch from the GEN-01 winner;
- change max_model_len;
- change model/quantization;
- change prompt/token budgets;
- change RAG graph;
- run Full240.

## Required tests

Configuration tests only where code/config plumbing changes.

At minimum:

1. Compose/env value reaches vLLM command.
2. invalid setting is not silently accepted if validation exists.
3. default remains documented.
4. benchmark manifest records the effective candidate setting after BMARK-15C.

Do not create fake performance unit tests.

## Validation

Focused config/compose tests and:

```powershell
docker compose config
```

No broad local suite unless Python code changes.

## Manual acceptance

Perform the controlled sweep.

For each run save:

```text
candidate_GEN-02_seq2.zip
candidate_GEN-02_seq3.zip
candidate_GEN-02_seq4.zip
```

or equivalent benchmark evidence.

## Final report

Return:

1. candidate matrix;
2. selected `max_num_seqs`;
3. wall-time delta;
4. tail-latency delta;
5. GPU/OOM observations;
6. quality/safety parity;
7. exact environment used.

Do not commit or push.
