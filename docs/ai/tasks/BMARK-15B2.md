# BMARK-15B2 — Streamed answer-generation token usage

**Branch:** `fix/streamed-generation-token-usage`

## Goal

Complete the BMARK-15B/BMARK-15B1 telemetry contract by recording authoritative token usage for streamed `answer_generation` requests.

The latest healthy Smoke30 benchmark already records:

```text
answer_generation request rate
answer_generation latency
answer_generation finish reason
```

but does **not** record:

```text
answer_generation input tokens
answer_generation output tokens
answer_generation total tokens
answer_generation output-token p50/p95/p99
```

Non-streaming request types such as:

```text
content_risk_scan
query_rewrite
answer_evaluation
```

already report token usage correctly.

This task must fix only the streamed usage gap.

---

## Current evidence

The current LLM service records token metrics only when provider usage is present:

```text
usage.input_tokens is not None
usage.output_tokens is not None
usage.total_tokens is not None
```

`answer_generation` uses streaming.

The current benchmark evidence therefore strongly suggests:

```text
streamed answer_generation
    ↓
provider/client streaming path
    ↓
final authoritative usage is not propagated
    ↓
generation.usage remains missing
    ↓
token metrics are skipped
```

Do not treat this hypothesis as proven until the active vLLM/OpenAI-compatible client path is inspected.

---

# Required outcome

For streamed `answer_generation`, the final completed request must expose the same authoritative usage contract as non-streaming calls:

```text
input_tokens
output_tokens
total_tokens
```

and the existing shared metrics must then record:

```text
ragapp_llm_tokens_total
ragapp_llm_output_tokens
```

for:

```text
request_type=answer_generation
traffic_class=eval|live
```

without changing generation content or streaming behavior.

---

# PART 1 — Inspect the active streaming provider path

Find the exact vLLM/OpenAI-compatible client implementation used by `llm_agent`.

Trace:

```text
LLMService.execute
    ↓
LLMInvocation
    ↓
llm_client.generate(...)
    ↓
streaming provider/client
    ↓
GenerationResult / usage
```

Determine whether the active OpenAI-compatible streaming API supports final usage via:

```text
stream_options.include_usage = true
```

or the equivalent supported by the actual client library/version.

Prefer provider-reported usage.

Do not guess from generic OpenAI API behavior if the repository uses a custom adapter.

---

# PART 2 — Preferred implementation

If the active provider supports authoritative streaming usage:

1. request usage in the streaming request;
2. capture the final usage-bearing stream chunk/event;
3. normalize it into the existing generation usage object;
4. return it through the same `generation.usage` contract used by non-streaming calls.

Conceptually:

```text
stream starts
    ↓
token chunks emitted normally
    ↓
final usage chunk arrives
    ↓
adapter stores:
  input_tokens
  output_tokens
  total_tokens
    ↓
GenerationResult.usage populated
```

Do not create a second token-accounting system inside `LLMService` if the provider adapter is the correct ownership boundary.

---

# PART 3 — No fake token accounting

Do **not** use:

```text
token_event_count
```

as authoritative token count unless the implementation proves one event always equals one tokenizer token.

Streaming callbacks may represent:

```text
text fragments
sub-token pieces
multiple tokens
provider chunks
```

depending on the adapter.

Therefore:

```text
token_event_count != guaranteed tokenizer token count
```

Do not silently substitute it for `usage.output_tokens`.

---

# PART 4 — Fallback behavior

If authoritative provider usage is genuinely unavailable in the current client/version:

Preferred fallback order:

1. use the exact tokenizer associated with the active served model, if already available safely in the adapter;
2. otherwise keep usage unavailable and document the limitation.

If tokenizer-derived counting is introduced:

```text
usage_source = estimated_tokenizer
```

must remain distinguishable from:

```text
usage_source = provider
```

Do not mix estimated and provider counts silently.

Do not download/load a second large tokenizer/model solely for telemetry unless it is already available or very cheap.

Do not introduce network dependency into request handling just to count tokens.

---

# PART 5 — Preserve streaming behavior

This task must not alter:

```text
token ordering
token text
first-token latency materially
stream termination
llm.done behavior
final answer text
```

The user-visible stream must remain functionally identical.

If `stream_options.include_usage=true` changes the final stream chunk shape, handle it without emitting usage metadata as visible answer text.

---

# PART 6 — Usage normalization

Reuse the existing usage model.

For a healthy streamed `answer_generation` request, expected normalized usage:

```text
provider
input_tokens
output_tokens
total_tokens
```

Required invariants:

```text
input_tokens >= 0
output_tokens >= 0
total_tokens >= input_tokens
total_tokens >= output_tokens
```

If provider semantics define:

```text
total_tokens = input_tokens + output_tokens
```

validate/preserve that where appropriate.

Do not fabricate `0` for unavailable fields.

Missing remains:

```text
None / null
```

---

# PART 7 — Metrics integration

The existing metrics added by BMARK-15B1 should work automatically once usage is present.

Verify that streamed `answer_generation` now contributes to:

```text
ragapp_llm_tokens_total{
  request_type="answer_generation",
  direction="input|output|total"
}
```

and:

```text
ragapp_llm_output_tokens{
  request_type="answer_generation"
}
```

Do not add duplicate counters/histograms if the existing instrumentation is sufficient.

Do not add high-cardinality labels.

---

# PART 8 — Finish reason

Preserve existing finish-reason behavior.

A healthy streamed answer must still record bounded normalized finish reason, e.g.:

```text
stop
length
error
```

Token-usage handling must not overwrite or lose final finish reason.

---

# PART 9 — Error handling

If the stream fails before authoritative usage is received:

```text
usage remains unavailable
```

unless provider usage was already safely captured.

Do not record zero usage for failed/incomplete streams.

Do not cause a secondary telemetry exception to mask the original generation error.

Telemetry must remain best-effort relative to generation correctness.

---

# PART 10 — Benchmark export expectations

No new benchmark export schema is required if BMARK-15B1 already captures:

```text
llm_input_token_rate
llm_output_token_rate
llm_total_token_rate
llm_finish_reason_rate
llm_output_tokens_p50_by_request_type
llm_output_tokens_p95_by_request_type
llm_output_tokens_p99_by_request_type
```

This task only needs to make `answer_generation` appear in those existing metrics.

Do not add redundant per-item raw token traces to the ZIP.

---

# PART 11 — Security / privacy

Do not log:

```text
prompt text
raw streamed answer
auth tokens
API keys
provider credentials
```

merely to debug usage accounting.

Token counts are safe telemetry.

Preserve existing redaction behavior.

---

# PART 12 — Tests

Follow repository policy:

```text
TEST WHAT CHANGED.
LET GITHUB CI TEST THE REPOSITORY.
```

At task start:

```powershell
python scripts/ai/check.py doctor
```

Run focused tests during implementation.

## Required provider/client tests

At least:

1. streaming request asks provider for usage when supported;
2. ordinary token chunks still reach `on_token`;
3. final usage chunk is captured and not emitted as visible text;
4. streamed result returns populated usage;
5. finish reason is preserved;
6. final answer text remains identical;
7. stream with no usage does not fabricate zeroes;
8. stream error before usage preserves original error behavior;
9. non-streaming behavior is unchanged.

## Required LLM service tests

10. streamed `answer_generation` with provider usage records input token counter.
11. records output token counter.
12. records total token counter.
13. records output-token histogram.
14. usage `None` still skips metrics rather than recording zero.
15. finish-reason metric still records once.
16. no duplicate metric observations occur.

## Required benchmark/metrics compatibility tests

17. BMARK-15B1 token queries require no schema change.
18. `answer_generation` samples are compatible with existing request_type grouping.
19. export sanitizer still does not redact safe numeric token metrics.
20. credential token fields remain redacted.

---

# PART 13 — Validation

Expected touched areas:

```text
llm_agent provider/client adapter
llm_agent service tests
possibly shared usage model/tests
possibly benchmark tests only if needed
```

Run:

```text
python scripts/ai/check.py focused llm_agent --files <changed> --tests <focused>
```

plus focused shared/RAG tests only if those files are touched.

Run Ruff on changed Python files.

Run mypy only if changed typed contracts fall in the normal CI scope.

Run the `llm_agent` affected suite once near completion.

Do not run the whole repository locally just for completeness.

GitHub CI remains authoritative.

---

# PART 14 — Manual acceptance after merge

After CI green and merge:

```powershell
git switch main
git pull
```

Rebuild/recreate:

```text
llm_agent
rag
```

Recreate vLLM only if the provider/client configuration change requires it.

Do not re-upload corpus files.

Run:

```text
Dataset: Smoke30
Profile: Full Diagnostic
```

Download:

```text
bmark15b2_smoke30.zip
```

---

# PART 15 — Manual ZIP acceptance

The ZIP must show `answer_generation` in:

```text
llm_input_token_rate
llm_output_token_rate
llm_total_token_rate

llm_output_tokens_p50_by_request_type
llm_output_tokens_p95_by_request_type
llm_output_tokens_p99_by_request_type

llm_finish_reason_rate
```

Expected:

```text
answer_generation output tokens > 0
answer_generation input tokens > 0
answer_generation total tokens > 0
```

for healthy generated answers.

Also verify:

```text
benchmark completed
actual failures = 0
timeouts = 0
```

and:

```text
no NaN
no Infinity
strict JSON parses
```

---

# PART 16 — Gate after this task

If the Smoke30 ZIP contains complete `answer_generation` usage:

```text
BMARK-15B2 = PASS
```

Then:

```text
BMARK-15B measurement window = CLOSED
```

Proceed to:

```text
GEN-04
→ GEN-01
→ GEN-02
```

Before GEN-03, analyze:

```text
answer_generation output p50/p95/p99
answer_evaluation output p50/p95/p99
content_risk_scan output p50/p95/p99
query_rewrite output p50/p95/p99
finish reasons
```

and choose budgets from evidence.

---

# Non-goals

Do not implement:

- GEN-01 RabbitMQ prefetch tuning;
- GEN-02 vLLM concurrency tuning;
- GEN-03 max-token changes;
- GEN-04 benchmark profiles;
- prompt changes;
- temperature/top-p changes;
- model replacement;
- retrieval changes;
- evaluator redesign;
- output guardrail redesign;
- SAFE-01;
- systemic benchmark fail-fast.

---

# Acceptance criteria

```text
[ ] Streamed answer generation exposes authoritative usage when provider supports it.
[ ] No visible stream regression.
[ ] No fake token_event_count accounting.
[ ] Missing usage is not converted to zero.
[ ] answer_generation contributes to input/output/total token counters.
[ ] answer_generation contributes to output-token histogram.
[ ] answer_generation appears in benchmark token p50/p95/p99.
[ ] finish reason remains correct.
[ ] non-streaming actions are unchanged.
[ ] focused tests pass.
[ ] llm_agent affected suite passes.
[ ] Smoke30 Full Diagnostic completes.
[ ] bmark15b2_smoke30.zip contains complete answer_generation token evidence.
```

---

# Final report

Return exactly:

1. Root cause of missing streamed usage.
2. Active provider/client path inspected.
3. Whether provider-reported usage or fallback is used.
4. Changed files grouped by:
   - provider/client
   - llm service
   - shared models/metrics if touched
   - tests
5. Streaming behavior before/after.
6. Usage fields now populated.
7. Metric behavior.
8. Focused/affected test counts.
9. Ruff/mypy result if applicable.
10. Manual Smoke30 acceptance still required.
11. Known limitation/deferred work.

Do not commit or push.
