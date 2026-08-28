# GEN-03C — Stabilize `answer_evaluation`: preserve provider finish reason and tune the evaluator token ceiling

**Branch:** `fix/answer-evaluation-truncation`

## Goal

Fix the real failure exposed by GEN-03B.

GEN-03B successfully removed the false `EvalEvidenceConsistencyError` attribution and preserved retrieval evidence across downstream graph failures. The remaining Smoke30 failures are now attributable to the actual downstream stage:

```text
failed_node = evaluate_answer_light
error_class = DownstreamRPCError

structured_output_invalid:
Structured output parse failed:
No valid JSON object found in model output
```

The strongest current hypothesis is that the `answer_evaluation` JSON output is sometimes being truncated at the existing:

```text
ANSWER_EVALUATION_MAX_TOKENS=512
```

The benchmark already shows the evaluator output distribution pressing against that ceiling:

```text
p50 ≈ 260
p95 ≈ 488
p99 ≈ 507
```

However, the current telemetry collapses provider finish reasons into `error` after parsing/validation fails, so we cannot yet prove whether those failures were originally:

```text
finish_reason = length
```

This task must:

1. preserve the **provider's original finish reason** independently from application parsing status;
2. prove whether evaluator parse failures correlate with `finish_reason=length`;
3. perform a controlled `512 vs 640 vs 768` evaluator-budget sweep;
4. choose the **smallest reliable evaluator ceiling**;
5. keep all other GEN settings fixed;
6. avoid changing prompts, retrieval, model serving, or vLLM version in the same experiment.

---

# Current fixed configuration

Keep fixed throughout this task:

```text
vLLM version = 0.27.1
Model Runner = V1

LLM_REQUEST_PREFETCH = 4
VLLM_MAX_NUM_SEQS = 4
VLLM_GPU_MEMORY_UTILIZATION = 0.80
VLLM_MAX_MODEL_LEN = 10240

ANSWER_GENERATION_MAX_TOKENS = 128
CONTENT_RISK_SCAN_MAX_TOKENS = 128
QUERY_REWRITE_MAX_TOKENS = 128
MEMORY_EXTRACTION_MAX_TOKENS = 512
```

Only this value may change during the controlled sweep:

```text
ANSWER_EVALUATION_MAX_TOKENS
```

Candidates:

```text
512
640
768
```

Do not change the current model:

```text
RedHatAI/Qwen3.5-4B-quantized.w4a16
```

Do not change quantization, temperature, top-p, prompts, retrieval, chunking, eval concurrency, queue prefetch, or `max_num_seqs`.

---

# PART 1 — Preserve provider finish reason separately from application status

## Problem

Current `llm_service` metric normalization effectively behaves like:

```python
if errored:
    finish_reason = "error"
```

This destroys important provider evidence.

Example:

```text
vLLM returns:
finish_reason = length

↓ parser receives truncated JSON

structured parse fails

↓ metric becomes:

finish_reason = error
```

We then cannot distinguish:

```text
model/provider ended because max_tokens was exhausted
```

from:

```text
provider completed normally but application parser failed
```

These are different failure modes.

---

## Required telemetry model

Preserve two independent concepts:

```text
provider_finish_reason
application_status
```

Example:

```text
provider_finish_reason = length
application_status = structured_output_invalid
```

or:

```text
provider_finish_reason = stop
application_status = success
```

Do not overwrite the provider finish reason because a later parser/validator failed.

---

# PART 2 — Metrics

Add or adapt bounded metrics so the following can be measured independently.

## Provider finish reason

Preferred bounded metric:

```text
ragapp_llm_provider_finish_reasons_total
```

labels:

```text
service
model
request_type
traffic_class
finish_reason
```

Bounded finish values only:

```text
stop
length
completed
content_filter
tool_calls
cancelled
other
unknown
```

Do **not** include application failure state in this label.

If no provider response was received:

```text
provider_finish_reason = unknown
```

Do not call it `error` unless the provider explicitly returned that finish reason.

---

## Application result status

Continue using a separate bounded status/error metric such as:

```text
success
execution_error
structured_output_invalid
timeout
```

Reuse an existing metric where possible rather than creating duplicate telemetry.

Do not create unbounded labels from error messages.

---

# PART 3 — Preserve per-request diagnostic evidence for benchmark runs

For benchmark diagnostics, record bounded safe evidence for each typed LLM action where available:

```text
request_type
provider_finish_reason
application_status
input_tokens
output_tokens
total_tokens
max_tokens
latency_ms
```

For structured-output failures additionally record:

```text
parse_stage
```

bounded to:

```text
parse
validation
unknown
```

Do **not** export:

```text
raw prompt
raw model output
answer text
retrieved context text
stack trace
tenant-sensitive text
```

The benchmark ZIP must allow us to answer:

> Did `answer_evaluation` hit its output ceiling before the parser failed?

without exposing model text.

---

# PART 4 — Preserve provider usage even when parsing fails

If the provider completed and returned usage before application parsing failed, preserve:

```text
input_tokens
output_tokens
total_tokens
provider_finish_reason
```

Do not discard usage just because:

```text
structured_output_invalid
```

occurred later.

This is required to diagnose whether failed evaluator calls consume approximately:

```text
512 output tokens
```

---

# PART 5 — Keep provider error semantics distinct

The following are not the same:

### A. Provider/inference failure

```text
HTTP error
connection failure
provider timeout
server unavailable
```

### B. Valid provider response, parser failure

```text
provider response received
usage known
finish reason known
JSON parser fails
```

### C. Valid JSON parse, schema validation failure

```text
provider response received
JSON extracted
Pydantic validation fails
```

Preserve these distinctions in internal status/error code.

Do not map all three to a generic `execution_error`.

---

# PART 6 — Do not change structured-output transport yet

This task runs against:

```text
vLLM 0.27.1
```

Do **not** migrate the provider payload from the current structured-output mechanism to the vLLM 0.28 `structured_outputs` API in this task.

Keep the current 0.27-compatible transport behavior fixed so the token-budget experiment has one independent variable.

The future `VLLM-028-01` task must separately migrate the adapter to the vLLM 0.28 structured-output API.

Do not combine that migration with this token sweep.

---

# PART 7 — Do not change the answer-evaluation prompt/schema

Keep the current `answer_evaluation` prompt and output model fixed.

In particular, do not:

- shorten the claim schema;
- remove claim-level evidence;
- remove passage IDs;
- remove hallucination severity;
- change the rubric;
- change the parser selection policy;
- loosen Pydantic validation;
- fabricate missing fields.

We need to determine whether the existing contract is reliable with a slightly larger output ceiling.

Prompt/schema optimization can be a later task if 768 still proves insufficient.

---

# PART 8 — Add explicit evaluator budget provenance

The benchmark manifest/export already records per-action budgets.

Ensure:

```text
llm.max_tokens.answer_evaluation
```

is present and numeric in every candidate ZIP.

Required values must distinguish:

```text
512
640
768
```

Do not rely on operator filenames alone.

Comparison compatibility must continue to treat a known evaluator-budget difference as:

```text
incompatible
```

for strict apples-to-apples provenance.

This is expected in a controlled tuning experiment.

---

# PART 9 — Add evaluator-failure summary

Add a bounded benchmark summary section for typed LLM application failures by request type.

Preferred shape:

```json
{
  "llm_action_failures": {
    "answer_evaluation": {
      "total": 6,
      "structured_output_invalid": 6,
      "execution_error": 0,
      "timeout": 0
    }
  }
}
```

Also summarize provider finish reasons for those failed calls where known.

Example:

```json
{
  "answer_evaluation_failure_finish_reasons": {
    "length": 6,
    "stop": 0,
    "unknown": 0
  }
}
```

Use bounded keys only.

Do not include arbitrary error strings as object keys.

---

# PART 10 — Focused tests

Follow:

```text
TEST WHAT CHANGED.
LET CI TEST THE REPOSITORY.
```

At task start:

```powershell
python scripts/ai/check.py doctor
```

If doctor is blocked by the known local pytest/plugin mismatch, use the already-documented repository workaround. Do not introduce a new plugin-autoload bypass.

Required tests:

## Provider result / finish reason

1. provider response with `finish_reason=stop` preserves `stop`;
2. provider response with `finish_reason=length` preserves `length`;
3. missing finish reason becomes `unknown` or existing bounded fallback;
4. application parse failure does not overwrite provider `length`;
5. application validation failure does not overwrite provider `stop`;
6. provider HTTP/connection failure has no fabricated provider finish reason.

## Usage

7. output token usage survives structured parse failure;
8. input/total usage survives validation failure;
9. no usage is fabricated when the provider never returned one.

## Metrics

10. provider finish-reason metric remains bounded;
11. application status metric remains separate;
12. no raw error message appears as a metric label.

## Benchmark diagnostics

13. per-action provider finish reason is exported safely;
14. failed evaluator calls keep output token count;
15. answer-evaluation max-token budget appears in provenance;
16. candidate budget differences affect comparison compatibility;
17. historical ZIP/manifests without the new fields remain readable;
18. strict JSON / `allow_nan=False` remains intact.

---

# PART 11 — Validation

Expected touched areas:

```text
backend/llm_agent/app/services/llm_service.py
backend/llm_agent/app/llm/implementations/vllm.py if needed
shared metrics definitions if needed
backend/rag benchmark Prometheus/diagnostic collection
benchmark summary/export
tests
```

Do not touch unrelated services.

Run:

```text
Ruff on changed Python files
```

Run focused tests during coding.

Near completion run affected suites for the actually changed services.

Because this crosses LLM telemetry into benchmark evidence, run affected checks for:

```text
llm_agent
rag
```

when supported by `scripts/ai/check.py`.

Run mypy only for changed typed code in normal CI scope.

GitHub CI remains authoritative.

---

# PART 12 — Manual baseline after instrumentation

After merge/rebuild, run **one diagnostic control**:

```text
Dataset: Smoke30
Profile: Smoke Quality

ANSWER_EVALUATION_MAX_TOKENS=512
```

Everything else fixed.

Save:

```text
gen03c_eval512_smoke30.zip
```

This run exists to prove whether the evaluator failures correspond to:

```text
provider_finish_reason = length
```

Do not change the prompt/schema between this and later candidates.

---

# PART 13 — 512 diagnostic decision

Inspect every failed:

```text
answer_evaluation
```

call.

For each, capture:

```text
provider_finish_reason
output_tokens
max_tokens
application_status
parse_stage
```

## Strong truncation evidence

Treat the truncation hypothesis as strongly confirmed if most/all evaluator parse failures show:

```text
provider_finish_reason = length
and
output_tokens near 512
```

Proceed to the 640/768 sweep.

## Hypothesis disproven

If failures mostly show:

```text
provider_finish_reason = stop
```

well below the token ceiling, do **not** increase the budget blindly.

Stop the sweep and report:

```text
GEN-03C token-ceiling hypothesis disproven
```

Then create a separate structured-output reliability task.

Do not paper over malformed normal-stop outputs by simply increasing `max_tokens`.

---

# PART 14 — Controlled budget sweep

If truncation is supported, run:

## Candidate A

```text
ANSWER_EVALUATION_MAX_TOKENS=512
```

Already captured as:

```text
gen03c_eval512_smoke30.zip
```

## Candidate B

```text
ANSWER_EVALUATION_MAX_TOKENS=640
```

Save:

```text
gen03c_eval640_smoke30.zip
```

## Candidate C

```text
ANSWER_EVALUATION_MAX_TOKENS=768
```

Save:

```text
gen03c_eval768_smoke30.zip
```

Between runs, change **only**:

```text
ANSWER_EVALUATION_MAX_TOKENS
```

Recreate only the services required for that environment/config change.

Do not rebuild/re-upload the corpus.

---

# PART 15 — Candidate acceptance

For each run compare:

```text
execution totals
answer_evaluation structured_output_invalid count
provider finish_reason distribution
answer_evaluation output-token p50/p95/p99
answer_evaluation latency p50/p95
phase wall time
queue wait
execution time
timeouts
guardrail outcomes
retrieval metrics
quality metrics
```

## Reliability gate

Preferred candidate:

```text
0 answer_evaluation structured_output_invalid failures
```

If a candidate still fails:

- inspect provider finish reason;
- inspect output token count;
- do not assume a larger ceiling is automatically correct.

## Selection rule

Choose the **smallest** budget that:

```text
eliminates or materially reduces truncation failures
without introducing reliability regressions
and without a material latency penalty
```

Do not choose 768 automatically if 640 is clean.

---

# PART 16 — Performance interpretation

Increasing max output tokens does **not** automatically increase latency when the model normally stops early.

Therefore compare actual observed:

```text
output_tokens
latency
wall time
```

Do not estimate cost from the configured ceiling.

A higher ceiling that the model rarely uses may be effectively free.

---

# PART 17 — Quality interpretation

Do not treat a single Smoke30 fluctuation in:

```text
groundedness
citation precision
citation recall
hallucination rate
```

as causal evidence by itself.

The main acceptance signal in this task is:

```text
structured-output reliability
```

Quality regression becomes credible if:

- repeated;
- deterministic;
- associated with new truncation/malformed output;
- or clearly tied to changed evaluator behavior.

Since the prompt/schema remains fixed, large quality movement should be investigated but not immediately attributed to the token ceiling.

---

# PART 18 — Safety datasets

Only after a winning evaluator budget is selected and Smoke30 is clean, run the pending GEN-03 safety checks:

```text
PromptInjection8
Unanswerable20
```

using the selected evaluator budget.

Save:

```text
gen03c_prompt_injection8.zip
gen03c_unanswerable20.zip
```

Required:

```text
no new safety regression
no structured evaluator failures
no unexpected truncation
no fabricated answer-quality values
```

Do not run Full240 yet.

---

# PART 19 — Keep GEN-03B correctness invariants

Do not regress the GEN-03B behavior.

For downstream evaluator failures:

```text
execution outcome = failed
original error preserved
failed_node preserved
final retrieval context preserved
retrieval metrics still valid
answer-quality metrics unmeasured
```

The new evaluator telemetry must not reintroduce:

```text
EvalEvidenceConsistencyError
```

or fake retrieval misses.

---

# PART 20 — Explicitly deferred

Do not implement in this task:

```text
vLLM 0.28 upgrade
CUDA image changes
Model Runner V2
FlashInfer/GDN forcing
max_num_batched_tokens tuning
performance_mode tuning
gpu_memory_utilization tuning
structured_outputs API migration
answer-evaluation prompt redesign
answer-evaluation schema simplification
memory-extraction tuning
retrieval changes
hybrid retrieval
reranker
```

These remain separate experiments.

---

# Acceptance criteria

```text
[ ] Provider finish reason is preserved independently from application status.
[ ] Provider usage survives parser/validation failure when the provider responded.
[ ] Benchmark ZIP exposes safe bounded evaluator failure diagnostics.
[ ] No raw prompt/output/context is exported.
[ ] 512 diagnostic proves or disproves the truncation hypothesis.
[ ] If supported, 512/640/768 sweep changes only the evaluator token ceiling.
[ ] Smallest reliable evaluator budget is selected.
[ ] GEN-03B retrieval/error-attribution invariants remain intact.
[ ] PromptInjection8 passes with the selected budget.
[ ] Unanswerable20 passes with the selected budget.
[ ] Full240 is not run yet.
```

---

# Final report

Return exactly:

1. Proven root cause or whether the truncation hypothesis was disproven.
2. Changed files grouped by:
   - provider/LLM telemetry
   - benchmark diagnostics/export
   - tests
3. New provider-finish-reason contract.
4. New application-status contract.
5. Proof usage survives structured-output failure.
6. Focused/affected test counts.
7. Ruff/mypy results.
8. CI result.
9. 512 diagnostic:
   - evaluator failure count
   - provider finish reasons
   - output-token distribution
10. 640 result.
11. 768 result.
12. Selected evaluator budget and why it is the smallest reliable value.
13. Wall-time and evaluator-latency deltas.
14. Quality comparison.
15. PromptInjection8 result.
16. Unanswerable20 result.
17. GEN-03B regression check.
18. Deferred items:
   - vLLM 0.28 structured-output migration;
   - CUDA/FlashInfer tuning;
   - evaluator prompt/schema redesign if still necessary.

Do not commit or push.
