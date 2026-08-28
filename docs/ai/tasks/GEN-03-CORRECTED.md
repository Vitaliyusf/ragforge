# GEN-03 — Implement and validate evidence-based per-action generation token budgets

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Branch:** `perf/per-action-generation-budgets`

## Goal

Replace the current single shared `vllm_max_tokens=512` behavior for normal typed LLM actions with **explicit per-request-type output-token budgets**, using the benchmark telemetry already collected.

This task is both:

1. an implementation task — wire per-action budgets all the way to the active vLLM invocation; and
2. a controlled validation task — prove the candidate budgets actually ran and did not introduce truncation, parsing failures, safety regressions, or material quality regressions.

Do **not** treat a benchmark run with all actions still at `512` as GEN-03 validation.

---

# Current measured evidence

Recent Smoke30 telemetry showed approximately:

```text
content_risk_scan:
  output p50 ≈ 25–30
  output p95 ≈ 60–75
  output p99 ≈ 90–110
  finish_reason=stop ≈ 100%

query_rewrite:
  output p50 ≈ 46–47
  output p95 ≈ 62
  output p99 ≈ 64
  finish_reason=stop ≈ 100%

answer_generation:
  output p50 ≈ 51–54
  output p95 ≈ 90–91
  output p99 ≈ 95
  finish_reason=stop ≈ 100%

answer_evaluation:
  output p50 ≈ 230–250
  output p95 ≈ 470–490
  output p99 ≈ 500–507
  finish_reason=length observed around 16–20%

memory_extraction:
  insufficient benchmark evidence to justify reducing the current budget
```

Therefore the **first controlled candidate** for this task is:

```text
answer_generation   = 128
content_risk_scan   = 128
query_rewrite       = 128

answer_evaluation   = 512
memory_extraction   = 512
```

Do not reduce `answer_evaluation` in this task.

Do not reduce `memory_extraction` without new evidence.

---

# Fixed performance configuration

GEN-03 must run with the winners from earlier controlled experiments fixed:

```text
primary LLM queue prefetch = 4
VLLM_MAX_NUM_SEQS = 4
```

Do not retune either variable here.

Keep fixed:

```text
model
quantization
gpu_memory_utilization
max_model_len
eval concurrency
retrieval config
embedding model
chunking
temperature
top_p
prompt versions
dataset
```

This task changes only the action-specific output-token ceilings.

---

# PART 1 — Add explicit per-action settings

Add typed configuration values in `llm_agent` for:

```text
answer_generation_max_tokens
answer_evaluation_max_tokens
content_risk_scan_max_tokens
query_rewrite_max_tokens
memory_extraction_max_tokens
```

Environment names:

```text
ANSWER_GENERATION_MAX_TOKENS
ANSWER_EVALUATION_MAX_TOKENS
CONTENT_RISK_SCAN_MAX_TOKENS
QUERY_REWRITE_MAX_TOKENS
MEMORY_EXTRACTION_MAX_TOKENS
```

Defaults for this task:

```text
ANSWER_GENERATION_MAX_TOKENS=128
ANSWER_EVALUATION_MAX_TOKENS=512
CONTENT_RISK_SCAN_MAX_TOKENS=128
QUERY_REWRITE_MAX_TOKENS=128
MEMORY_EXTRACTION_MAX_TOKENS=512
```

Preserve existing special-case summary behavior:

```text
SUMMARY_MAX_TOKENS
```

must remain independent.

Do not collapse summarization back into the new normal action map.

---

# PART 2 — Central budget resolver

Create one authoritative resolver for typed request budgets.

Conceptually:

```python
def max_tokens_for_request_type(request_type: str) -> int:
    ...
```

or an equivalent typed mapping owned by the LLM service/config layer.

Required mapping:

```text
answer_generation  → answer_generation_max_tokens
answer_evaluation  → answer_evaluation_max_tokens
content_risk_scan  → content_risk_scan_max_tokens
query_rewrite      → query_rewrite_max_tokens
memory_extraction  → memory_extraction_max_tokens
```

Any other typed action must use a deliberate fallback.

Preferred fallback:

```text
vllm_max_tokens
```

Do not silently map an unknown request type to one of the five action budgets.

Do not scatter `if request_type == ...` token limits across handlers.

---

# PART 3 — Wire the budget into the actual provider invocation

This is the critical implementation requirement.

The selected per-action value must reach the object passed into the active provider/client path.

Conceptually:

```text
request.request_type
    ↓
resolve max_tokens
    ↓
LLMInvocation(max_tokens=<resolved>)
    ↓
VLLM client
    ↓
OpenAI-compatible /v1/completions request
    ↓
max_tokens=<resolved>
```

If the existing `LLMInvocation` already has an optional `max_tokens` field, use it.

If the provider already honors:

```text
invocation.max_tokens or config.vllm_max_tokens
```

preserve that ownership.

Do not introduce a second unrelated max-token parameter in a lower layer.

---

# PART 4 — Prove the provider request uses the resolved value

Add focused tests at the provider/client boundary.

Required proof:

```text
answer_generation request
→ outbound provider payload max_tokens == 128

answer_evaluation request
→ max_tokens == 512

content_risk_scan request
→ max_tokens == 128

query_rewrite request
→ max_tokens == 128

memory_extraction request
→ max_tokens == 512
```

A config unit test alone is **not enough**.

The test must verify the value reaches the actual invocation/provider payload or the closest deterministic adapter boundary.

This requirement exists because the previous run still executed with all actions at 512.

---

# PART 5 — Preserve context-window safety

The context-window calculation must reserve the **effective action-specific output budget**, not always the old global 512.

Conceptually:

```text
allowed_input_tokens
=
max_model_len
- resolved_output_budget
- existing safety margin
```

Do not allow:

```text
input + requested output > effective context window
```

Preserve any current truncation/safety behavior.

Summary continues to reserve `SUMMARY_MAX_TOKENS`.

If structured actions already use additional context reservations, preserve them.

---

# PART 6 — Structured output safety

These actions require especially careful handling:

```text
content_risk_scan
answer_evaluation
memory_extraction
query_rewrite
```

Where an action requires valid structured output:

- keep current structured-output/guided-JSON behavior;
- preserve parser and Pydantic validation;
- do not convert truncation into a fake valid default;
- preserve `structured_output_invalid` or existing explicit error semantics.

For each structured action, test a response near the configured token boundary.

Do not accept malformed JSON merely to make the lower budget pass.

---

# PART 7 — Finish-reason evidence

Continue recording normalized provider finish reasons.

GEN-03 acceptance must examine:

```text
stop
length
error
```

by `request_type`.

The main regression signal for a reduced budget is:

```text
finish_reason=length increases materially
```

especially for:

```text
answer_generation
content_risk_scan
query_rewrite
```

Candidate acceptance requires no meaningful new truncation pattern.

---

# PART 8 — Add effective budgets to benchmark provenance

This is mandatory.

The benchmark manifest/export must record the **effective per-action budgets actually used**.

Preferred manifest shape:

```json
{
  "llm": {
    "chat_model": "...",
    "max_model_len": 10240,
    "quantization": "...",
    "max_tokens": {
      "answer_generation": 128,
      "answer_evaluation": 512,
      "content_risk_scan": 128,
      "query_rewrite": 128,
      "memory_extraction": 512
    }
  }
}
```

or a similarly explicit stable schema consistent with existing manifest conventions.

Do not rely only on `.env` or operator notes.

A downloaded ZIP must be sufficient to answer:

> Which token budget did this benchmark actually run with?

Add these fields to strict comparison compatibility if changing them would make benchmark quality/performance comparisons non-apples-to-apples.

A known budget difference between candidate and baseline must not be silently reported as fully compatible.

---

# PART 9 — Compose / env wiring

Update:

```text
.env.example
docker-compose.yml
```

so the five settings are explicit and reproducible.

For `llm_agent`, pass:

```text
ANSWER_GENERATION_MAX_TOKENS
ANSWER_EVALUATION_MAX_TOKENS
CONTENT_RISK_SCAN_MAX_TOKENS
QUERY_REWRITE_MAX_TOKENS
MEMORY_EXTRACTION_MAX_TOKENS
```

For `rag`, inject the same safe numeric values if benchmark manifest construction happens inside RAG and requires them for provenance.

Do not capture arbitrary llm_agent environment.

Use the existing safe provenance allowlist pattern.

---

# PART 10 — Startup observability

At `llm_agent` startup, log a bounded configuration summary containing:

```text
primary prefetch
max concurrent requests
default vllm_max_tokens
answer_generation_max_tokens
answer_evaluation_max_tokens
content_risk_scan_max_tokens
query_rewrite_max_tokens
memory_extraction_max_tokens
```

Do not log secrets, API keys, URLs with credentials or prompt data.

This should let an operator verify the active values before starting a benchmark.

---

# PART 11 — Validation constraints

Configuration validation should reject nonsensical values.

At minimum:

```text
max_tokens >= 1
```

Use a reasonable upper bound consistent with the configured context window / existing Pydantic style.

Do not silently clamp an invalid operator value unless the repository has an established clamping convention.

Prefer fail-fast configuration validation.

---

# PART 12 — Required tests

Follow:

```text
TEST WHAT CHANGED.
LET CI TEST THE REPOSITORY.
```

At task start:

```powershell
python scripts/ai/check.py doctor
```

Run focused tests during implementation.

## Config tests

1. defaults resolve to 128/512/128/128/512.
2. each env variable overrides independently.
3. invalid zero/negative values fail validation.
4. legacy `vllm_max_tokens` remains fallback for unknown/unmapped normal action.
5. `SUMMARY_MAX_TOKENS` remains independent.

## Resolver tests

6. answer_generation → 128.
7. answer_evaluation → 512.
8. content_risk_scan → 128.
9. query_rewrite → 128.
10. memory_extraction → 512.
11. unknown action → deliberate fallback.

## Invocation/provider tests

12. answer_generation provider payload uses 128.
13. answer_evaluation provider payload uses 512.
14. content_risk_scan provider payload uses 128.
15. query_rewrite provider payload uses 128.
16. memory_extraction provider payload uses 512.
17. streamed answer_generation still captures usage.
18. finish reason remains intact.
19. provider error behavior remains intact.
20. summary still uses its summary-specific budget.

## Context-window tests

21. answer_generation reserves 128 output tokens.
22. answer_evaluation reserves 512.
23. summary reserves SUMMARY_MAX_TOKENS.
24. oversized input cannot violate max_model_len.

## Structured-output tests

25. content_risk_scan valid JSON still parses under 128.
26. query_rewrite valid output still parses under 128.
27. answer_evaluation validation remains unchanged.
28. truncated structured output remains an explicit error, not fabricated success.

## Benchmark provenance/export tests

29. all five budgets appear in manifest.
30. all five budgets survive diagnostic export.
31. numeric budgets are not redacted.
32. old manifests remain readable.
33. missing budget provenance is `unknown`, not assumed equal.
34. known different critical token budgets affect compatibility appropriately.

---

# PART 13 — Local validation

Expected affected areas:

```text
llm_agent config
llm service / invocation resolver
vLLM adapter/provider tests
rag benchmark manifest/comparison
docker-compose.yml
.env.example
```

Run focused checks for changed files/services.

Run Ruff on changed Python files.

Run mypy only if touched typed contracts are in normal CI scope.

Near completion run affected suites for:

```text
llm_agent
rag benchmark manifest/comparison
```

according to repository policy.

Run:

```powershell
docker compose config
```

Do not run the whole repository locally solely for completeness.

GitHub CI remains authoritative.

---

# PART 14 — Manual pre-benchmark verification

After merge:

```powershell
git switch main
git pull
```

Rebuild/recreate affected services:

```text
llm_agent
rag
```

Before starting any benchmark, verify inside the running containers.

Example intent:

```text
llm_agent:
answer_generation=128
answer_evaluation=512
content_risk_scan=128
query_rewrite=128
memory_extraction=512

rag manifest environment:
same five effective values
```

Use an existing config/debug mechanism or a safe one-line Python settings print.

Do not print secrets.

If any value still shows 512 incorrectly:

```text
STOP
```

and fix wiring before spending another Smoke30 run.

---

# PART 15 — Controlled Smoke30 candidate

Run:

```text
Dataset: Smoke30
Profile: Smoke Quality
```

Fixed:

```text
primary prefetch = 4
VLLM_MAX_NUM_SEQS = 4
```

Candidate:

```text
answer_generation = 128
answer_evaluation = 512
content_risk_scan = 128
query_rewrite = 128
memory_extraction = 512
```

Download:

```text
gen03_candidate_smoke30.zip
```

---

# PART 16 — Smoke30 acceptance

The ZIP must prove the effective token budgets.

Required run health:

```text
30 items accounted
0 unexpected failures
0 timeouts
expected guardrail blocks remain explicit
```

Compare against the current 512-all baseline.

Review at least:

```text
phase_wall_clock_ms
queue_wait_ms
execution_ms
total_elapsed_ms
LLM p50/p95 by request_type
token p50/p95/p99 by request_type
finish_reason distribution
structured parse failures
groundedness
citation precision
citation recall
hallucination/unsupported rate
```

## Truncation gate

For reduced actions:

```text
answer_generation
content_risk_scan
query_rewrite
```

there must not be a meaningful new `finish_reason=length` pattern.

A single anomalous observation should be inspected, not automatically accepted or rejected.

## Answer evaluation

Expected to remain:

```text
512
```

Its pre-existing `length` observations are not caused by the reduced budgets in the other actions.

Do not declare this task a failure solely because answer_evaluation still shows historical 512-ceiling pressure.

That issue is a separate future optimization question.

---

# PART 17 — Safety regression suites

If Smoke30 passes, run:

```text
PromptInjection8
Unanswerable20
```

using the appropriate existing evaluation path/profile.

The exact profile may be Regular E2E / Smoke Quality equivalent if these datasets are supported there.

Do not run Extended unless acceptance specifically requires it.

Required checks:

## PromptInjection8

- no safety regression;
- no new structured-output failures;
- no guardrail bypass attributable to truncation;
- no unexpected `length` termination in risk scan.

## Unanswerable20

- refusal/abstention behavior remains intact;
- no new hallucination pattern;
- no truncated generation that converts an abstention into an unsupported answer.

Save:

```text
gen03_prompt_injection8.zip
gen03_unanswerable20.zip
```

if the workflow produces benchmark archives for those runs.

---

# PART 18 — Candidate decision

Choose the 128/512/128/128/512 candidate only if:

```text
[ ] provider-level tests prove the values are used
[ ] benchmark provenance proves the values are used
[ ] Smoke30 is healthy
[ ] reduced actions do not develop length truncation
[ ] structured outputs remain valid
[ ] PromptInjection8 passes
[ ] Unanswerable20 passes
[ ] no material quality regression is supported by evidence
```

A performance improvement is desirable but **not required** to keep a safer smaller ceiling if behavior is equivalent and it meaningfully reduces worst-case decode exposure.

However, do not claim performance improvement unless measured.

---

# PART 19 — Do not tune answer_evaluation in this task

Current evidence:

```text
p99 ≈ 500+
finish_reason=length ≈ 16–20%
```

Therefore:

```text
ANSWER_EVALUATION_MAX_TOKENS=512
```

must remain unchanged here.

Create a separate follow-up only if later evidence justifies testing:

```text
512 vs 640 vs 768
```

Such a test must evaluate:

```text
structured validity
evaluation quality
latency
token cost
length finish rate
```

Do not mix it into GEN-03.

---

# PART 20 — Do not tune memory_extraction in this task

There is not enough benchmark evidence yet.

Keep:

```text
MEMORY_EXTRACTION_MAX_TOKENS=512
```

until a workload that actually exercises memory extraction provides output-token distributions and finish reasons.

---

# PART 21 — No Full240 yet

Do **not** run Full240 immediately after this task.

GEN-03 is still a Smoke/safety-gate optimization step.

The first large checkpoint remains after the generation optimization sequence is complete.

---

# Out of scope

Do not change:

- LLM queue prefetch;
- VLLM_MAX_NUM_SEQS;
- gpu_memory_utilization;
- max_model_len;
- prompts;
- temperature;
- top_p;
- retrieval;
- embedding;
- chunking;
- evaluator schema;
- guardrail policy;
- streaming safety architecture;
- SAFE-01;
- hybrid retrieval;
- reranking.

---

# Acceptance criteria

```text
[ ] Five per-action token settings exist.
[ ] Candidate defaults are 128/512/128/128/512.
[ ] Central resolver maps request_type deterministically.
[ ] Resolved budget reaches the actual vLLM provider request.
[ ] Summary remains independent.
[ ] Context-window reservation uses the effective action budget.
[ ] Structured-output semantics remain strict.
[ ] Effective budgets are recorded in benchmark provenance.
[ ] ZIP proves which budgets ran.
[ ] Focused/affected tests pass.
[ ] docker compose config passes.
[ ] Smoke30 candidate passes.
[ ] PromptInjection8 passes.
[ ] Unanswerable20 passes.
[ ] No material new length truncation appears in reduced actions.
[ ] No Full240 is run yet.
```

---

# Final report

Return exactly:

1. Why the previous all-512 run was not a GEN-03 candidate.
2. Changed files grouped by:
   - llm_agent config
   - budget resolver/service
   - provider/client
   - benchmark provenance
   - Compose/env
   - tests
3. Effective candidate budgets.
4. Proof each request type reaches the provider with the expected `max_tokens`.
5. Context-window reservation behavior.
6. Benchmark provenance shape.
7. Focused/affected test counts.
8. Ruff/mypy/Compose results.
9. Manual container config verification result.
10. Smoke30 result.
11. PromptInjection8 result.
12. Unanswerable20 result.
13. Measured performance delta versus all-512 baseline.
14. Finish-reason/truncation comparison.
15. Quality/safety comparison.
16. Deferred items:
    - answer_evaluation 512-vs-640/768 experiment;
    - memory_extraction tuning after sufficient evidence.

Do not commit or push.
