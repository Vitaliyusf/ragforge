# GEN-03 — Per-request-type LLM output budgets

**Branch:** `perf/llm-action-token-budgets`

## Goal

Replace one broad default output-token budget with bounded per-action budgets derived from measured output distributions.

This task targets runaway tails, unnecessary decoding work, token cost, and timeout risk.

## Dependency

Complete BMARK-15B first so token usage and latency are observable by `request_type`.

Prefer completing GEN-01 and GEN-02 first so concurrency is stable before token-budget experiments.

## Problem

Different LLM actions have very different output shapes:

```text
answer_generation   -> 1–3 short sentences
content_risk_scan   -> small structured JSON
query_rewrite       -> short rewrite/subqueries
answer_evaluation   -> larger structured JSON with claims
memory_extraction   -> potentially larger structured output
```

One shared `max_tokens` value is inefficient and makes tail behavior harder to control.

## Required design

Add project-consistent per-action output-token settings, conceptually:

```text
ANSWER_GENERATION_MAX_TOKENS
ANSWER_EVALUATION_MAX_TOKENS
CONTENT_RISK_SCAN_MAX_TOKENS
QUERY_REWRITE_MAX_TOKENS
MEMORY_EXTRACTION_MAX_TOKENS
```

Use naming consistent with existing `Settings`.

Pass the action-specific budget into `LLMInvocation.max_tokens`.

Keep an explicit fallback default for legacy callers.

## Budget selection

Do not invent arbitrary small values.

Use BMARK-15B evidence:

```text
output token p50
p95
p99/max
finish_reason
structured parse failures
```

Choose each budget from observed distribution plus safety margin.

Document the rule.

Example only:

```text
budget = observed p99 + bounded safety margin
```

Do not copy this formula blindly if the sample size is too small.

## Special care: answer evaluation

`answer_evaluation` may produce claim arrays and therefore needs more room than simple risk scan JSON.

Do not truncate it aggressively just to improve speed.

## Special care: structured JSON

A smaller budget must not create new:

```text
finish_reason=length
structured_output_invalid
parse fallback
missing claims
```

## Required measurements

Before/after on Smoke30:

```text
phase wall-clock
LLM output tokens by action
finish_reason distribution
structured parse errors
timeouts
quality metrics
citation metrics
guardrail outcomes
```

## Non-goals

Do not:

- change prompts substantially;
- combine evaluator and guardrail;
- change model/quantization;
- change retrieval;
- tune concurrency in the same PR;
- run Full240 during development.

## Required tests

At least:

1. each typed action resolves its own max token budget.
2. legacy/unknown action uses safe fallback.
3. request-specific budget reaches vLLM payload.
4. answer evaluation can still emit expected structured output.
5. risk scan keeps structured JSON behavior.
6. invalid config values are rejected/normalized safely.
7. defaults preserve existing behavior unless explicitly configured.

## Validation

Doctor once.
Focused llm_agent config/service/client tests.
Ruff changed files.
Run llm_agent affected suite once near completion.

## Manual acceptance

Run:

```text
Smoke30 Regular E2E
```

and, if generation/security behavior changed materially:

```text
PromptInjection8
Unanswerable20
```

Do not run Full240.

## Final report

Return:

1. observed token distributions used;
2. selected per-action budgets;
3. before/after wall time;
4. finish_reason/parse-error comparison;
5. quality/safety parity;
6. test results.

Do not commit or push.
