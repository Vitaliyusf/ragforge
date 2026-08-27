# LLM output-token budgets

Typed LLM actions can override the legacy `VLLM_MAX_TOKENS` fallback with:

- `ANSWER_GENERATION_MAX_TOKENS`
- `ANSWER_EVALUATION_MAX_TOKENS`
- `CONTENT_RISK_SCAN_MAX_TOKENS`
- `QUERY_REWRITE_MAX_TOKENS`
- `MEMORY_EXTRACTION_MAX_TOKENS`

All overrides are optional positive integers. An unset typed override inherits
`VLLM_MAX_TOKENS`, including for legacy or unknown callers, so upgrading does
not change output limits by itself.

## Selection rule

Set an override only after a representative Smoke30 run has enough successful
samples for that action. Review output-token p50, p95, p99/max, finish reasons,
structured parse failures, timeouts, and quality/safety results. Use the
observed upper tail plus a bounded safety margin. With a small sample, keep the
legacy fallback instead of treating a noisy maximum as a production limit.

After configuring a budget, repeat Smoke30 and reject the change if it adds
`finish_reason=length`, structured-output failures, missing evaluator claims,
timeouts, or quality/citation/guardrail regressions. `answer_evaluation` needs a
larger margin than small JSON actions because its claim arrays can vary in size.
