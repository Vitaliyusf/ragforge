# GEN-03E — Stabilize `answer_evaluation` with provider-constrained JSON on vLLM 0.27.1

**Branch:** keep the current working branch unless the operator explicitly changes it.  
**Do not commit or push.**

## Context

The controlled GEN-03D evaluator ceiling sweep is complete on:

```text
vLLM = 0.27.1
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

Only `ANSWER_EVALUATION_MAX_TOKENS` changed across the sweep:

```text
512 -> 4 evaluator failures
640 -> 4 evaluator failures
768 -> 6 evaluator failures
```

Important evidence:

- `q004` hit the exact evaluator ceiling at 512, 640, and 768 and failed with `finish_reason=length`.
- `q014` hit the exact evaluator ceiling at 512, 640, and 768 and failed with `finish_reason=length`.
- Some items also failed with `finish_reason=stop` plus `structured_output_invalid`.
- Therefore `max_tokens` is not the root cause. It is only the termination boundary for unstable structured generation.
- Do not continue increasing the evaluator ceiling.
- The next controlled experiment is provider-constrained JSON / JSON Schema on the same vLLM version.

## Goal

Test whether provider-constrained structured output makes `answer_evaluation` reliable without changing the evaluator rubric, Pydantic output model, retrieval path, model, quantization, concurrency, or vLLM version.

The experiment must isolate exactly one variable:

```text
legacy/free-form structured-output transport
vs
provider-constrained JSON-schema transport
```

Use:

```text
vLLM 0.27.1
ANSWER_EVALUATION_MAX_TOKENS=512
```

for both sides.

## Hard invariants

Keep fixed:

```text
VLLM_IMAGE=vllm/vllm-openai:v0.27.1
VLLM_USE_V2_MODEL_RUNNER=0
VLLM_MAX_MODEL_LEN=10240
VLLM_GPU_MEMORY_UTILIZATION=0.80
VLLM_MAX_NUM_SEQS=4
LLM_REQUEST_PREFETCH=4

ANSWER_GENERATION_MAX_TOKENS=128
ANSWER_EVALUATION_MAX_TOKENS=512
CONTENT_RISK_SCAN_MAX_TOKENS=128
QUERY_REWRITE_MAX_TOKENS=128
MEMORY_EXTRACTION_MAX_TOKENS=512
```

Do not change:

- model
- quantization
- temperature
- top_p
- prompt wording
- answer-evaluation rubric
- answer-evaluation Pydantic model
- retrieval settings
- benchmark concurrency
- queue prefetch
- max_num_seqs
- gpu_memory_utilization
- max_num_batched_tokens
- performance_mode
- prefix caching
- GDN backend
- attention backend
- Model Runner
- CUDA image/version
- corpus/index
- benchmark dataset

## Part 1 — Capability probe first

Before changing production request behavior, prove which constrained-output mechanism is supported by the currently running vLLM 0.27.1 OpenAI-compatible endpoint.

Use the existing served model and the existing authenticated adapter path.

Preferred mechanisms, in order:

1. OpenAI-compatible `response_format` with JSON Schema if supported.
2. vLLM `structured_outputs` / equivalent supported field if that is the correct 0.27.1 API for this endpoint.

Do not guess parameter names. Inspect the installed/runtime API behavior or existing vLLM compatibility code and add a focused capability test.

The capability probe must:

- use a tiny synthetic schema;
- return valid JSON;
- prove schema enforcement;
- fail cleanly if unsupported;
- never log secrets or raw production prompts.

If vLLM 0.27.1 does not support an appropriate constrained JSON-schema mechanism, STOP and report that fact. Do not silently redesign prompts or upgrade to 0.28 in this task.

## Part 2 — Derive schema from the authoritative Pydantic model

The JSON Schema must be generated from the existing `answer_evaluation` Pydantic output model.

Do not maintain a second hand-written schema.

Required rule:

```text
Pydantic model
    -> model_json_schema()
    -> provider constrained-output payload
    -> provider response
    -> existing application parser/normalizer
    -> Pydantic validation remains authoritative
```

Application-side Pydantic validation must remain in place even when the provider claims schema-constrained output.

## Part 3 — Scope constrained output to `answer_evaluation`

Do not change every typed LLM action yet.

Apply the new transport only to:

```text
request_type = answer_evaluation
```

Other typed actions remain on the existing transport.

This keeps the experiment causally interpretable.

## Part 4 — Preserve telemetry contracts

Do not regress GEN-03C/GEN-03D evidence.

For every evaluator request, preserve:

```text
request_type
provider_finish_reason
application_status
parse_stage
input_tokens
output_tokens
total_tokens
max_tokens
latency_ms
```

For a provider/protocol failure, preserve the distinction between:

```text
provider_protocol_error
provider_http_error
provider_timeout
structured_output_invalid
validation_error
```

Reuse bounded existing status/error metrics where possible.

Do not create unbounded metric labels.

## Part 5 — Add transport provenance

Benchmark manifest/export must make the evaluator transport explicit.

Preferred shape:

```json
{
  "llm": {
    "structured_output_transport": {
      "answer_evaluation": "legacy"
    }
  }
}
```

or:

```json
{
  "llm": {
    "structured_output_transport": {
      "answer_evaluation": "json_schema"
    }
  }
}
```

This field must affect strict benchmark compatibility.

Historical ZIPs without it must remain readable and report unknown/null rather than crash.

## Part 6 — Fix the two known observability gaps while touching this path

### A. Nested safe metric sanitizer

Current exported nested vLLM metric evidence still redacts:

```text
cache_config_info.metric.kv_cache_size_tokens
```

even though it is safe numeric telemetry.

Fix narrowly with a path-aware numeric allowlist.

Do not weaken credential redaction or arbitrary token-shaped string redaction.

### B. Observed vLLM provenance

The warmup/runtime probe can observe `/version`, but benchmark manifests still emit:

```text
vllm.observed.server_version = null
```

Wire the observed runtime evidence into the benchmark manifest/export when safely available.

Keep conceptual separation:

```text
configured.image
configured.server_version
observed.server_version
```

Do not infer `observed.server_version` from the image tag.

If no runtime observation is available, keep it null.

## Part 7 — Run-delta metrics

Where benchmark ZIPs already contain Prometheus counter snapshots before and after a run, add a safe derived `run_delta` block for cumulative counters.

At minimum, when data is available:

```text
preemptions
generation_tokens
prompt_tokens
prefix_cache_hits
prefix_cache_queries
```

Do not fabricate deltas if either side is missing.

Do not subtract gauges.

## Part 8 — Focused tests

Follow:

```text
TEST WHAT CHANGED.
LET CI TEST THE REPOSITORY.
```

Required tests:

1. capability probe accepts supported JSON-schema transport;
2. unsupported transport fails explicitly and does not silently fall back;
3. evaluator schema is generated from the authoritative Pydantic model;
4. constrained transport is used only for `answer_evaluation`;
5. other request types remain unchanged;
6. provider `finish_reason=stop` remains preserved;
7. provider `finish_reason=length` remains preserved;
8. application parser/validation status remains separate;
9. usage survives structured-output failure;
10. transport provenance is exported;
11. transport difference makes strict benchmark comparison incompatible;
12. historical manifests remain readable;
13. nested `kv_cache_size_tokens` exports as a numeric safe value;
14. arbitrary secret/token-like strings remain redacted;
15. observed server version comes from runtime observation rather than image parsing;
16. missing observed version remains null;
17. counter `run_delta` values are correct;
18. gauges are not incorrectly differenced;
19. strict JSON / `allow_nan=False` remains intact;
20. GEN-03B retrieval evidence semantics remain intact.

## Part 9 — Validation before live benchmark

Run:

```text
git diff --check
Ruff on changed Python files
focused llm_agent tests
focused rag benchmark/export/provenance tests
runtime contract tests
```

Run repository doctor first.

If the known project pytest/pytest-asyncio mismatch blocks authoritative local tests, keep isolated-scratch validation clearly labeled as non-authoritative.

Do not introduce a plugin-autoload bypass.

## Part 10 — Deployment gate

Before the measured run:

1. root `.env` must resolve to:

```text
VLLM_IMAGE=vllm/vllm-openai:v0.27.1
VLLM_USE_V2_MODEL_RUNNER=0
ANSWER_EVALUATION_MAX_TOKENS=512
```

2. run:

```powershell
docker compose config
```

3. verify the running container image, not only Compose intent.

4. rebuild/recreate any changed `rag` and `llm_agent` services.

5. if vLLM was restarted/recreated, run the representative warmup again.

6. representative warmup must cover:
   - tiny request;
   - ~2500–3500 token prefill;
   - four concurrent short requests;
   - warm-state repeat if JIT occurs.

7. any JIT after the benchmark measurement boundary contaminates timing.

## Part 11 — Controlled benchmark pair

Run the SAME Smoke30 / Smoke Quality benchmark twice on vLLM 0.27.1.

### Control A — legacy transport

```text
ANSWER_EVALUATION_MAX_TOKENS=512
answer_evaluation structured output transport = legacy
```

Save:

```text
gen03e_v0271_eval512_legacy_smoke30.zip
```

### Candidate B — JSON-schema constrained transport

```text
ANSWER_EVALUATION_MAX_TOKENS=512
answer_evaluation structured output transport = json_schema
```

Save:

```text
gen03e_v0271_eval512_jsonschema_smoke30.zip
```

Change no other variable.

## Part 12 — Required comparison

Compare:

```text
execution totals
answer_evaluation structured_output_invalid count
provider finish_reason distribution
length failures
stop+parse failures
output-token p50/p95/p99
answer_evaluation latency p50/p95/p99
phase wall time
queue wait
execution time
preemptions run_delta
retrieval metrics
answer quality with denominators
```

Explicitly report the behavior of:

```text
q004
q014
```

These are known persistent runaway cases.

## Acceptance gate

Preferred candidate:

```text
30 total
28 normal graph successes
2 expected guardrail blocks
0 evaluator failures
0 answer_evaluation structured_output_invalid
0 length+parse failures
0 stop+parse failures
```

The JSON-schema candidate is accepted only if:

```text
- evaluator reliability is materially improved;
- no provider/protocol instability is introduced;
- q004 and q014 no longer run to the 512-token ceiling;
- retrieval metrics remain unchanged within expected deterministic behavior;
- no safety semantics are weakened;
- latency regression is not material relative to the reliability gain.
```

If the candidate is still unreliable, STOP.

Do not:
- increase max_tokens again;
- redesign the evaluator prompt;
- simplify the evaluator schema;
- upgrade to vLLM 0.28;
- begin PromptInjection8;
- begin Unanswerable20;
- start performance tuning.

Report the failure mode and create the next task only after evidence review.

## Part 13 — Brain / project-memory update

At task completion, update project memory with durable, evidence-backed findings only.

Supersede the old hypothesis:

```text
"answer_evaluation likely just needs a larger max_tokens ceiling"
```

with:

```text
"GEN-03D controlled sweep on vLLM 0.27.1 showed no reliability improvement from 512 -> 640 -> 768. Persistent q004/q014 failures hit the exact configured ceiling at all three budgets, and normal-stop malformed JSON also occurred. max_tokens is not the root cause; constrained structured generation is the next controlled variable."
```

Also record durable rules:

```text
- candidate runtime versions must not become stable defaults before acceptance;
- JIT after benchmark measurement start contaminates performance timing;
- dirty worktrees require source fingerprinting before authoritative baselines;
- service tests must not depend on repository CWD through implicit root .env loading;
- provider finish reason and application status are independent facts.
```

Do not store:
- credentials;
- raw prompts;
- model outputs;
- tenant data;
- temporary experiment state as durable memory.

## Explicitly deferred

Do not implement in this task:

```text
vLLM 0.28 upgrade
CUDA 12.9/13 comparison
Model Runner V2
gpu_memory_utilization sweep
max_num_batched_tokens tuning
performance_mode tuning
prefix cache ON/OFF
forced FlashInfer GDN
prompt redesign
schema simplification
retrieval changes
hybrid retrieval
CrossEncoder
Full240
```

## Final report

Return:

1. changed files grouped by subsystem;
2. capability-probe result;
3. exact constrained-output API used;
4. proof schema is generated from the Pydantic model;
5. telemetry/provenance changes;
6. nested sanitizer fix result;
7. observed vLLM provenance result;
8. run-delta result;
9. focused test counts;
10. Ruff/mypy result;
11. project doctor result;
12. CI result;
13. legacy Smoke30 result;
14. JSON-schema Smoke30 result;
15. q004 comparison;
16. q014 comparison;
17. evaluator failure counts by finish reason;
18. token distributions;
19. latency/wall-time comparison;
20. preemption deltas;
21. quality comparison with denominators;
22. keep/reject decision;
23. memory records updated;
24. deferred next steps.

Do not commit or push.
