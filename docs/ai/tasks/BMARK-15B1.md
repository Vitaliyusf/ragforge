# BMARK-15B1 — Complete safe LLM token telemetry for benchmark analysis

**Branch:** `fix/benchmark-llm-token-telemetry`

## Goal

Finish the BMARK-15B telemetry contract so benchmark artifacts expose safe, usable LLM token and finish-reason evidence by request type.

This is a **small follow-up** to BMARK-15B.

Do not change benchmark scoring, generation behavior, prompts, model settings, RabbitMQ concurrency, vLLM concurrency, or token budgets in this task.

---

## Why this task exists

The latest healthy BMARK-15B Smoke30 run completed successfully and the latency split now works:

```text
queue_wait_ms
execution_ms
total_elapsed_ms
phase_wall_clock_ms
```

The LLM latency telemetry also works by request type.

However, the diagnostic ZIP still has an evidence gap:

```json
"llm_output_token_rate": "[redacted]"
```

The export sanitizer currently treats keys containing the word `token` as secret-looking, which is correct for credential fields such as:

```text
access_token
refresh_token
auth_token
bearer_token
api_token
```

but incorrect for safe numeric telemetry such as:

```text
llm_output_token_rate
llm_input_token_rate
llm_total_token_rate
```

Additionally, the current benchmark Prometheus snapshot does not expose enough token-distribution evidence to choose per-action generation budgets for GEN-03 safely.

We need this task to make GEN-03 evidence-based rather than guess-based.

---

# PART 1 — Preserve credential redaction

Do **not** weaken credential redaction globally.

The following kinds of fields must remain redacted:

```text
password
secret
api_key
apikey
authorization
access_token
refresh_token
auth_token
bearer_token
session_token
private_token
```

Use the smallest safe design.

Preferred approaches, in order:

1. explicit safe allowlist for known benchmark metric keys;
2. context-aware sanitizer behavior for numeric Prometheus telemetry;
3. more precise secret-key regex that distinguishes credential tokens from metric names.

Do not replace the current redaction rule with a broad rule that allows any key containing `token`.

---

# PART 2 — Safe benchmark token metrics

Extend the benchmark Prometheus snapshot so the pipeline section exposes, grouped by bounded labels:

```text
request_type
traffic_class
```

At minimum:

```text
llm_input_token_rate
llm_output_token_rate
llm_total_token_rate
```

Conceptual PromQL:

```text
sum by (request_type, traffic_class) (
  rate(ragapp_llm_tokens_total{direction="input"}[5m])
)

sum by (request_type, traffic_class) (
  rate(ragapp_llm_tokens_total{direction="output"}[5m])
)

sum by (request_type, traffic_class) (
  rate(ragapp_llm_tokens_total{direction="total"}[5m])
)
```

Use the current project metric names exactly.

Do not add tenant, benchmark id, request id, trace id, item id, conversation id, or prompt text as metric labels.

---

# PART 3 — Finish-reason telemetry

Expose bounded finish-reason evidence by:

```text
request_type
traffic_class
finish_reason
```

using the existing `ragapp_llm_finish_reasons_total` metric.

The benchmark snapshot should make it possible to see whether a candidate introduced:

```text
length
stop/completed
error
other bounded normalized reasons
```

Use the project's existing normalized finish-reason vocabulary.

Do not expose arbitrary provider strings if the service already bounds them.

Conceptual metric:

```text
llm_finish_reason_rate
```

Do not convert missing evidence to zero.

Missing/unobserved remains `null` or absent according to the benchmark evidence contract.

---

# PART 4 — Output-token distribution

GEN-03 needs more than average output-token rate.

Add a bounded Prometheus histogram for output-token count per LLM request.

Conceptual metric name:

```text
ragapp_llm_output_tokens
```

or a project-consistent equivalent.

Required labels:

```text
service
request_type
traffic_class
```

Do not label by:

```text
model
```

unless the current LLM metric cardinality convention strongly requires it and the model set is known bounded.

Prefer the smallest useful label set.

## Observation point

Observe the histogram once per completed LLM request when:

```text
usage.output_tokens is not None
```

Do not coerce missing provider usage to zero.

Do not observe failed requests with unknown token usage as zero.

## Buckets

Choose buckets suitable for the current known request types and output sizes.

The histogram must be useful for:

```text
content_risk_scan
query_rewrite
answer_generation
answer_evaluation
memory_extraction
```

A reasonable bounded bucket set may look conceptually like:

```text
8
16
32
64
96
128
192
256
384
512
768
1024
```

but inspect current usage and existing max-token defaults first.

Do not blindly copy these values if repository evidence suggests a better bounded set.

The final bucket set must be documented in code/tests.

---

# PART 5 — Benchmark quantiles

Extend benchmark Prometheus snapshot queries to expose at least:

```text
llm_output_tokens_p50_by_request_type
llm_output_tokens_p95_by_request_type
llm_output_tokens_p99_by_request_type
```

grouped by:

```text
request_type
traffic_class
```

using histogram quantiles over the new output-token histogram.

Conceptually:

```text
histogram_quantile(
  0.50,
  sum by (request_type, traffic_class, le) (
    rate(ragapp_llm_output_tokens_bucket[5m])
  )
)
```

and equivalent p95/p99 queries.

Keep the snapshot bounded.

Do not add per-item token rows to Prometheus.

---

# PART 6 — Optional mean tokens/request

If the current snapshot shape can expose it cleanly, add:

```text
llm_output_tokens_per_request
```

computed from:

```text
output token rate / request rate
```

grouped by request type and traffic class.

This is optional because p50/p95/p99 are the priority.

If denominator is zero or unavailable:

```text
null
```

not zero and not Infinity.

Do not add custom benchmark-only arithmetic if Prometheus can express it safely.

---

# PART 7 — Safe export behavior

The diagnostic ZIP must export these metric keys without redacting them:

```text
llm_input_token_rate
llm_output_token_rate
llm_total_token_rate
llm_finish_reason_rate
llm_output_tokens_p50_by_request_type
llm_output_tokens_p95_by_request_type
llm_output_tokens_p99_by_request_type
```

provided their values are numeric/list Prometheus result structures.

Credential-like keys must still redact.

Continue current normalization:

```text
NaN
"NaN"
+Inf
-Inf
Infinity
```

to:

```json
null
```

Continue:

```python
allow_nan=False
```

for exported JSON.

Do not expose raw prompt/output text as part of this task.

---

# PART 8 — Backward compatibility

Older benchmark runs created before the new histogram/query exists must remain exportable.

Expected behavior:

```text
new metric unavailable
→ null / empty metric result / unobserved
```

according to the existing snapshot contract.

Do not fail historical exports because a metric did not exist when the run was captured.

---

# PART 9 — Scope discipline

Do not change:

```text
LLM_REQUEST_PREFETCH
VLLM_MAX_NUM_SEQS
LLM max_tokens
prompt versions
temperature
top_p
retrieval config
eval concurrency
guardrail behavior
answer evaluator behavior
benchmark phase selection
```

No performance tuning belongs in this PR.

This task only makes the next performance tasks measurable.

---

# PART 10 — Tests

Follow repository policy:

```text
TEST WHAT CHANGED.
LET GITHUB CI TEST THE REPOSITORY.
```

At task start:

```powershell
python scripts/ai/check.py doctor
```

Run focused tests only during implementation.

## Required shared/LLM metrics tests

At least:

1. output-token histogram exists when Prometheus support is available.
2. histogram labels are bounded.
3. request with `usage.output_tokens=42` observes 42.
4. request with `usage.output_tokens=None` does not observe zero.
5. failed request with unknown usage does not fabricate token count.
6. finish-reason metric remains bounded.
7. existing token counters continue to work.

## Required benchmark Prometheus tests

8. input token rate query exists.
9. output token rate query exists.
10. total token rate query exists.
11. finish reason query exists.
12. output token p50 query exists.
13. output token p95 query exists.
14. output token p99 query exists.
15. queries group by bounded request_type/traffic_class only.
16. Prometheus query failure remains best-effort and does not fail benchmark.

## Required export sanitizer tests

17. `access_token` is redacted.
18. `refresh_token` is redacted.
19. `authorization` is redacted.
20. `api_key` is redacted.
21. `llm_output_token_rate` is **not** redacted.
22. `llm_input_token_rate` is **not** redacted.
23. `llm_total_token_rate` is **not** redacted.
24. output-token quantile metric keys are **not** redacted.
25. numeric Prometheus metric structures survive sanitization.
26. `"NaN"` / Infinity variants still normalize to null.
27. strict JSON export still uses `allow_nan=False`.

---

# PART 11 — Validation

Run focused checks for changed services/files.

Expected affected areas:

```text
shared metrics
llm_agent
rag benchmark Prometheus/export
```

Run Ruff on changed Python files.

Run mypy only if touched contracts fall in normal CI mypy scope.

Near completion run the relevant affected suites once:

```text
llm_agent
rag
shared tests relevant to metrics/export
```

Do not run the full local repository solely for completeness.

GitHub CI remains authoritative.

---

# PART 12 — Manual acceptance after merge

After PR merge and CI green:

```powershell
git switch main
git pull
```

Rebuild/recreate affected services:

```text
llm_agent
rag
```

and Prometheus only if configuration/scrape wiring changed.

Do not re-upload the 56 core corpus files.

Run:

```text
Dataset: Smoke30
Profile: Full Diagnostic
```

Full Diagnostic is intentional because we need telemetry for:

```text
content_risk_scan
answer_generation
answer_evaluation
query_rewrite
```

Download:

```text
bmark15b1_smoke30.zip
```

---

# PART 13 — Manual ZIP acceptance

The ZIP must show:

```text
benchmark completed
actual failures = 0
timeouts = 0
```

and safe token telemetry:

```text
llm_input_token_rate
llm_output_token_rate
llm_total_token_rate
llm_finish_reason_rate

llm_output_tokens_p50_by_request_type
llm_output_tokens_p95_by_request_type
llm_output_tokens_p99_by_request_type
```

The above must **not** equal:

```text
"[redacted]"
```

Credential fields must still redact.

Also verify:

```text
no NaN
no Infinity
strict JSON parses
```

---

# PART 14 — Gate to GEN-03

BMARK-15B1 is complete only when the new ZIP gives enough evidence to estimate per-action output budgets.

Before implementing GEN-03, provide the ZIP for analysis.

The decision inputs should include at least:

```text
answer_generation output token p50/p95/p99
answer_evaluation output token p50/p95/p99
content_risk_scan output token p50/p95/p99
query_rewrite output token p50/p95/p99
finish_reason distribution
```

If one request type has too few observations for meaningful p99:

- do not invent a budget from p99;
- use the available distribution plus current max-token contract and a documented safety margin;
- consider a targeted extra sample later.

---

# Out of scope

Do not implement:

- GEN-01 RabbitMQ prefetch tuning;
- GEN-02 vLLM concurrency tuning;
- GEN-03 token budget changes;
- GEN-04 benchmark profiles;
- GEN-05 post-generation call reduction;
- systemic dependency fail-fast;
- SAFE-01;
- retrieval/reranking changes.

A systemic benchmark dependency-outage fail-fast task may be created separately later.

---

# Acceptance criteria

```text
[ ] Safe numeric token metrics are not redacted.
[ ] Credential token fields remain redacted.
[ ] Input/output/total token rates are captured.
[ ] Finish reasons are captured by request type.
[ ] Output-token histogram exists.
[ ] Output-token p50/p95/p99 are captured.
[ ] Missing usage is not recorded as zero.
[ ] No high-cardinality metric labels were added.
[ ] Historical benchmark export remains compatible.
[ ] NaN/Infinity normalization remains correct.
[ ] Focused + affected tests pass.
[ ] Smoke30 Full Diagnostic completes.
[ ] bmark15b1_smoke30.zip contains usable token evidence.
```

---

# Final report

Return exactly:

1. Summary of telemetry gap fixed.
2. Changed files grouped by:
   - shared metrics
   - llm_agent recording
   - benchmark Prometheus
   - export sanitizer
   - tests/docs
3. Secret-redaction behavior before/after.
4. Token metrics and labels added.
5. Histogram bucket choice and rationale.
6. Benchmark queries added.
7. Focused/affected test counts.
8. Ruff/mypy result if applicable.
9. Manual Smoke30 acceptance still required.
10. Known limitation/deferred work.

Do not commit or push.
