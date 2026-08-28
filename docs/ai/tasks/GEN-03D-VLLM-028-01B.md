# GEN-03D / VLLM-028-01B — Close evaluator reliability, repair benchmark evidence, and establish a clean vLLM 0.28.0-cu129 A/B

**Branch:** `perf/vllm-028-upgrade`  
**Do not commit or push.**  
**This task supersedes the unfinished experimental portions of `GEN-03C` and the corrective work in `VLLM-028-01A`.**

---

# Goal

Finish the evaluator-reliability investigation and make the vLLM 0.27.1 → 0.28.0 comparison trustworthy enough to guide the next performance experiment.

This task exists because the latest real `gen03c_eval512_smoke30.zip` and vLLM startup/runtime log revealed that the code-side GEN-03C instrumentation is useful, but the experiment is still not clean enough to close GEN-03C or to accept/reject vLLM 0.28.

The task must proceed in **gated stages** so each measurement has one interpretable independent variable.

The order is:

```text
A. Preserve the current GEN-03C work and repair evidence/export gaps
    ↓
B. Establish a clean warmed vLLM 0.27.1 evaluator control at 512
    ↓
C. Finish the 512 → 640 → 768 evaluator-budget decision
    ↓
D. If normal-stop malformed JSON remains, test structured-output constraints separately
    ↓
E. Run PromptInjection8 + Unanswerable20 on the selected evaluator configuration
    ↓
F. Run clean version-only 0.27.1 vs 0.28.0-cu129 A/B
    ↓
G. Decide keep/repeat/rollback and recommend the next vLLM tuning experiment
```

Do **not** combine evaluator-budget changes, structured-output transport changes, CUDA image changes, scheduler tuning, and vLLM version changes in a single measured comparison.

---

# Latest observed evidence — treat this as the starting state

The latest uploaded diagnostic was intended to be the GEN-03C `512` control, but it was not run under the task's required 0.27.1 environment.

## Runtime actually used

Observed startup/runtime:

```text
vLLM server version = 0.28.0
Model Runner = V1
model = RedHatAI/Qwen3.5-4B-quantized.w4a16
quantization = compressed-tensors
max_model_len = 10240
max_num_seqs = 4
gpu_memory_utilization = 0.80
prefix caching = enabled
chunked prefill = enabled
```

The benchmark manifest recorded:

```text
vllm.image = vllm/vllm-openai:v0.28.0
vllm.server_version = 0.28.0
```

This was the **generic** `v0.28.0` image, not the intended first candidate:

```text
vllm/vllm-openai:v0.28.0-cu129
```

Therefore:

```text
latest GEN-03C run = diagnostic only
latest GEN-03C run != authoritative 0.27.1 evaluator control
latest GEN-03C run != authoritative 0.28-cu129 candidate
```

## Smoke30 execution result

```text
30 total
21 success
7 failed
2 guardrail_blocked
0 timed_out
```

All seven failures were:

```text
failed_node = evaluate_answer_light
error_class = DownstreamRPCError
application_status = structured_output_invalid
parse_stage = parse
```

Provider finish reasons for those seven failures:

```text
length = 5
stop   = 2
```

Failure item IDs from the diagnostic ZIP:

```text
length:
q003
q014
q018
q019
q023

stop:
q004
q239
```

This is an important conclusion:

```text
512-token truncation is a real major failure mode,
but it is not proven to be the only structured-output failure mode.
```

Five `length` failures strongly support the token-ceiling hypothesis.

The two `stop + structured_output_invalid + parse` failures must **not** be explained away by simply raising `max_tokens`.

## Evaluator token distribution

Prometheus-derived `answer_evaluation` output-token distribution in the same run:

```text
p50 ≈ 238.5
p95 ≈ 485.4
p99 ≈ 506.7
configured ceiling = 512
```

This strongly supports saturation near the 512 ceiling.

However, the per-call benchmark evidence that should prove the exact token count is still redacted.

## Critical GEN-03C export bug still present

The new `llm_actions` evidence correctly preserves:

```text
request_type
provider_finish_reason
application_status
parse_stage
latency_ms
```

but the benchmark sanitizer still exports safe numeric fields as:

```text
"[redacted]"
```

including:

```text
input_tokens
output_tokens
total_tokens
max_tokens
```

The same sanitizer problem still affects safe vLLM telemetry such as:

```text
generation_token_rate
generation_tokens_total
prompt_token_rate
prompt_tokens_total
inter_token_latency_p50
inter_token_latency_p95
kv_cache_size_tokens
max_num_batched_tokens
```

Therefore GEN-03C has **not** fully met its evidence acceptance criteria yet.

We can say:

```text
5/7 failed evaluator calls ended with provider_finish_reason=length
```

but we still cannot prove from the exported per-call artifact:

```text
output_tokens == 512
max_tokens == 512
```

until the sanitizer is fixed and the diagnostic is repeated.

## GEN-03B invariants remained healthy

Retrieval remained essentially identical to the post-GEN-03B result:

```text
MRR      = 0.9791667
Recall@5 = 1.0
Hit@1    = 0.9583333
```

No `EvalEvidenceConsistencyError` reappeared.

This supports:

```text
GEN-03B retrieval/error-attribution semantics remain intact.
```

Do not regress them in this task.

## Performance result is contaminated and non-authoritative

Latest phase wall time:

```text
~136.82s
```

Previous post-GEN-03B reference was approximately:

```text
~115s
```

Do **not** call this an 0.28 regression.

The latest vLLM log shows a measured-window JIT compile:

```text
Triton kernel JIT compilation during inference:
batch_memcpy_kernel
```

The warning occurred after benchmark start.

The latest Prometheus snapshot also shows:

```text
num_preemptions_total:
0 before run
23 after run
```

So all 23 preemptions occurred during the measured interval.

The runtime still had:

```text
Available KV cache memory ≈ 0.48 GiB
GPU KV cache size = 11,421 tokens
Maximum concurrency at 10,240 tokens/request ≈ 1.12x
peak logged KV usage ≈ 89.3%
```

vLLM itself reported that substantially more free GPU memory could potentially be used for KV cache.

This means:

```text
version-only A/B must stay at gpu_memory_utilization=0.80,
but GPU-memory/KV tuning remains the highest-priority follow-up
if preemptions remain after the version decision.
```

## Backend selection observed in generic vLLM 0.28.0

Observed automatic backend selection:

```text
sampling backend       = FlashInfer
GDN prefill backend     = Triton/FLA
GDN decode kernel       = cuda
attention backend       = FlashAttention 2
quantized linear kernel = MarlinLinearKernel
```

Important:

```text
generic vLLM 0.28.0 did NOT automatically switch this machine/model to FlashInfer GDN prefill.
```

Do not force a GDN backend in this task.

The `-cu129` candidate must again use automatic backend selection and record what actually happens.

## Prefix caching

Observed:

```text
prefix caching enabled
prefix cache hits = 0
prefix cache hit rate = 0%
```

Do not disable prefix caching during the version-only A/B because that would add another variable.

Prefix caching ON/OFF remains a later independent experiment.

## Model-info probe still wrong

The latest log still shows repeated:

```text
GET /v1/models/RedHatAI/Qwen3.5-4B-quantized.w4a16 -> 404
```

while:

```text
GET /v1/models -> 200
```

The known-404 model-specific probe must be removed.

## Runtime-version provenance still needs a real observation

The latest log contains no observed request to:

```text
GET /version
```

The server advertises `/version`, but the runtime provenance collector must actually query it.

Do not infer observed server version solely from the configured image tag.

## Security issue remains active

The latest startup log again contains the configured vLLM API key inside the `non-default args` line.

The exposed key must be rotated by the operator.

Never copy the replacement key into:

```text
benchmark ZIP
task output
startup evidence
chat
logs intended for sharing
```

---

# Fixed RAGForge settings

Unless a gated evaluator-budget stage explicitly changes `ANSWER_EVALUATION_MAX_TOKENS`, preserve:

```text
model = RedHatAI/Qwen3.5-4B-quantized.w4a16
quantization = compressed-tensors

LLM_REQUEST_PREFETCH=4
VLLM_MAX_NUM_SEQS=4
VLLM_GPU_MEMORY_UTILIZATION=0.80
VLLM_MAX_MODEL_LEN=10240

ANSWER_GENERATION_MAX_TOKENS=128
CONTENT_RISK_SCAN_MAX_TOKENS=128
QUERY_REWRITE_MAX_TOKENS=128
MEMORY_EXTRACTION_MAX_TOKENS=512

prefix caching = enabled
VLLM_USE_V2_MODEL_RUNNER=0
```

Do not change during the evaluator-budget or version-only experiments:

```text
retrieval
chunking
corpus
embedding model
Qdrant configuration
RabbitMQ prefetch
eval_run_concurrency
max_num_seqs
gpu_memory_utilization
max_num_batched_tokens
performance_mode
async scheduling
stream_interval
KV-cache bytes
attention backend
GDN backend
linear backend
speculative decoding
MTP
prompts
answer-evaluation schema
```

---

# PART 1 — Preserve current uncommitted GEN-03C work

The GEN-03C implementation currently sits on:

```text
perf/vllm-028-upgrade
```

and Claude previously reported an uncommitted working tree.

Do not reset, discard, or recreate the changes blindly.

At task start:

```powershell
python scripts/ai/check.py doctor
git status --short
git branch --show-current
git rev-parse HEAD
git diff --stat
git diff -- backend/llm_agent backend/rag backend/shared docker-compose.yml .env.example scripts tests
```

If `doctor` is blocked by the known local pytest/pytest-asyncio mismatch, use the already documented scratch-venv procedure.

Do not introduce `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` as authoritative validation.

Keep the existing GEN-03C contracts unless a test proves they are wrong:

```text
provider_finish_reason:
stop | length | completed | content_filter | tool_calls | cancelled | other | unknown

application_status:
success | provider_error | structured_output_invalid | timeout |
execution_error | streaming_not_supported | invalid_request

parse_stage:
parse | validation | unknown
```

Provider finish reason must never be overwritten by a later parser/validator failure.

Provider usage must survive parse/validation failure when the provider returned usage.

---

# PART 2 — Fix safe numeric export redaction completely

This is now a correctness blocker for GEN-03C and a performance-observability blocker for VLLM-028.

## Required safe numeric fields

Preserve numeric/null values for the exact bounded benchmark evidence paths that include `token` in their name.

At minimum:

### Per-action evidence

```text
llm_actions[*].input_tokens
llm_actions[*].output_tokens
llm_actions[*].total_tokens
llm_actions[*].max_tokens
```

### LLM summary distributions

```text
llm_actions.output_tokens.*
```

including any bounded:

```text
count
min
max
mean
p50
p95
p99
```

### vLLM metrics/provenance

```text
generation_token_rate
generation_tokens_total
prompt_token_rate
prompt_tokens_total
inter_token_latency_p50
inter_token_latency_p95
kv_cache_size_tokens
max_num_batched_tokens
```

Also preserve safe numeric/null descendants of exact known vLLM metric objects where the field is explicitly allowlisted.

## Do not globally whitelist token-like keys

Do **not** globally preserve arbitrary keys containing:

```text
token
secret
key
auth
credential
```

Credential-shaped data must remain redacted, including:

```text
api_key
VLLM_API_KEY
HF_TOKEN
access_token
refresh_token
auth_token
bearer_token
Authorization
Bearer ...
```

For safe-token exceptions, only preserve:

```text
int
float
null
explicit bounded enum/string where separately approved
```

Never allow an arbitrary string through because its key happens to be on a numeric telemetry path.

## Required sanitizer regression tests

Must prove preserved:

```text
input_tokens=1234
output_tokens=512
total_tokens=1746
max_tokens=512
kv_cache_size_tokens=11421
max_num_batched_tokens=null
max_num_batched_tokens=8192
generation_tokens_total=<number>
prompt_tokens_total=<number>
generation_token_rate=<number>
prompt_token_rate=<number>
inter_token_latency_p50=<number>
inter_token_latency_p95=<number>
```

Must prove redacted:

```text
api_key="secret"
VLLM_API_KEY="secret"
HF_TOKEN="secret"
access_token="secret"
refresh_token="secret"
some_token="arbitrary secret string"
Authorization="Bearer secret"
```

Keep:

```text
json.dumps(..., allow_nan=False)
```

No `NaN` or `Infinity`.

---

# PART 3 — Strengthen GEN-03C evidence tests

Add focused tests that prove a failed structured evaluator call survives all the way into the benchmark artifact as bounded safe evidence.

Required test shape:

```text
request_type = answer_evaluation
provider_finish_reason = length
application_status = structured_output_invalid
parse_stage = parse
input_tokens = numeric
output_tokens = numeric
max_tokens = numeric
total_tokens = numeric
latency_ms = numeric
```

And independently:

```text
provider_finish_reason = stop
application_status = structured_output_invalid
parse_stage = parse
```

The export must not contain:

```text
raw_output
raw_prompt
system_prompt
answer text
context text
stack trace
arbitrary downstream error text as a metric label
```

Historical ZIP/manifests without the new fields must remain readable.

Do not regress GEN-03B behavior:

```text
failure outcome remains failed
original error preserved
failed_node preserved
final retrieval context preserved
retrieval metrics valid when retrieval completed
answer-quality null/unmeasured when evaluator failed
EvalEvidenceConsistencyError does not mask downstream failure
```

---

# PART 4 — Correct vLLM image and local `.env` handling

## Tracked candidate default

Use:

```text
vllm/vllm-openai:v0.28.0-cu129
```

not generic:

```text
vllm/vllm-openai:v0.28.0
```

Update as appropriate:

```text
docker-compose.yml
.env.example
runtime contract tests
```

Expected Compose default:

```yaml
image: ${VLLM_IMAGE:-vllm/vllm-openai:v0.28.0-cu129}
```

## Local root `.env` is mandatory experiment state

For the 0.27.1 control:

```env
VLLM_IMAGE=vllm/vllm-openai:v0.27.1
VLLM_USE_V2_MODEL_RUNNER=0
```

For the 0.28 candidate:

```env
VLLM_IMAGE=vllm/vllm-openai:v0.28.0-cu129
VLLM_USE_V2_MODEL_RUNNER=0
```

The task must actually modify the local root `.env` between runs.

Do not rely on Compose defaults while `.env` overrides them.

`.env` must remain ignored and untracked.

Never print its secrets.

Before every run prove the effective image using:

```powershell
docker compose config
```

and, where useful:

```powershell
docker compose images
docker inspect <vllm-container>
```

If effective image does not match the intended experiment:

```text
STOP
```

Do not benchmark.

---

# PART 5 — Keep Model Runner V2 disabled

Preserve:

```env
VLLM_USE_V2_MODEL_RUNNER=0
```

in:

```text
docker-compose.yml
.env.example
local .env
```

Do not enable:

```text
Model Runner V2
VLLM_WSL2_ENABLE_PIN_MEMORY=1
MTP
speculative decoding
```

If startup reports V2:

```text
STOP
```

---

# PART 6 — Replace warmup with a measurable warmup gate

The latest 0.28 diagnostic still JIT-compiled `batch_memcpy_kernel` during the benchmark window.

A warmup script is not sufficient unless we can prove it ran **before** benchmark measurement and covered the relevant shapes.

## Warmup sequence

Before every measured Smoke30 run perform:

### A. tiny request

```text
1 request
small synthetic prompt
max_tokens <= 8
```

### B. representative prefill

```text
1 synthetic/non-sensitive request
~2500–3500 input tokens
max_tokens <= 32
```

Do not use benchmark questions or corpus text.

### C. concurrency shape

```text
4 concurrent requests
same /v1/completions path used by the application
short synthetic prompts
max_tokens <= 16 each
wait for all four
```

### D. second concurrency pass if needed

Because `batch_memcpy_kernel` appeared on a concurrent benchmark shape, allow one additional identical bounded 4-request pass if the first pass is what triggers JIT.

Do not keep warming indefinitely.

## Warmup evidence

Record bounded metadata such as:

```text
warmup_started_at
warmup_completed_at
warmup_shapes
warmup_success
```

Do not store prompts.

Before benchmark start verify:

```text
/health = healthy
/v1/models = served model present
no OOM
no provider error
runner = V1
```

The benchmark start timestamp must be later than `warmup_completed_at`.

## JIT contamination rule

Capture/inspect vLLM logs using timestamps.

If a monitored JIT warning occurs:

```text
benchmark_started_at <= JIT timestamp <= benchmark_finished_at
```

then:

```text
performance_contaminated = true
```

The run may be used for correctness diagnostics but **not** as authoritative A/B performance evidence.

Repeat once from the now-warm server.

Do not enable verbose/high-overhead JIT tracing for normal benchmark runs.

---

# PART 7 — Fix runtime model/version probes

## Readiness

Keep:

```text
GET /health
```

for server health.

Keep:

```text
GET /v1/models
```

for served-model discovery.

Locate the configured model in:

```json
data[]
```

Remove repeated calls to:

```text
GET /v1/models/{model}
```

because the active vLLM server returns 404 there.

Required test:

```text
client discovers model through /v1/models without issuing /v1/models/{id}
```

## Observed server version

Actually query:

```text
GET /version
```

when available.

Do not derive observed runtime version from the image tag.

If `/version` is unavailable:

```text
observed.server_version = null/unobserved
```

Do not guess.

---

# PART 8 — Separate configured and observed vLLM provenance

Use existing manifest conventions, but maintain the semantic distinction:

```json
{
  "vllm": {
    "configured": {
      "image": "vllm/vllm-openai:v0.28.0-cu129",
      "model_runner": "v1",
      "max_num_seqs": 4,
      "gpu_memory_utilization": 0.8,
      "max_model_len": 10240,
      "prefix_caching": true
    },
    "observed": {
      "server_version": "0.28.0",
      "model_runner": "v1",
      "max_model_len": 10240
    }
  }
}
```

Exact schema may differ if compatibility requires preserving the existing manifest shape.

Rules:

```text
configured image != observed runtime proof
missing observed value = null/unobserved
```

Critical comparison fields must continue to produce:

```text
known same      -> same
known different -> incompatible
missing         -> unknown
```

The explicit 0.27.1 vs 0.28.0 experiment is expected to be version-incompatible under strict compatibility semantics.

Do not hide the difference to make the comparison appear apples-to-apples.

## Build provenance warning

The latest ZIP still had incomplete/stale build provenance fields.

Do not perform a large provenance redesign here.

But final report must state whether these are trustworthy:

```text
build.git_sha
build.git_branch
build.build_timestamp
build.image_tag
```

If incomplete/stale:

```text
build_provenance_status = incomplete
```

This A/B remains a development experiment, not Official Baseline V1.

---

# PART 9 — Capture bounded runtime backend evidence

For both control and candidate, record safe bounded evidence when observable:

```text
server_version
CUDA runtime/version
PyTorch CUDA version
GPU architecture / compute capability
FlashInfer version
sampling backend
GDN prefill backend
GDN decode backend
attention backend
linear/quantization kernel
chunked_prefill
prefix_caching
max_num_batched_tokens
performance_mode
async_scheduling
```

Use bounded enums where practical.

Examples:

```text
gdn_prefill_backend:
flashinfer | triton_fla | other | unobserved

attention_backend:
flash_attn | flashinfer | triton | flex | other | unobserved

linear_backend:
marlin | flashinfer | triton | other | unobserved
```

Do not export full raw startup lines.

Do not guess from documentation.

For the first candidate keep:

```text
GDN backend = auto
attention backend = auto
linear backend = auto
```

Do not force FlashInfer GDN in this task.

---

# PART 10 — Rotate and protect exposed secrets

Immediate operator action:

```text
rotate the VLLM_API_KEY that appeared in previously shared startup logs
```

Do not print the replacement value.

If startup logs are captured or parsed, redact at least:

```text
api_key
VLLM_API_KEY
HF_TOKEN
Authorization
Bearer ...
access_token
refresh_token
```

Prefer extracting only known-safe bounded startup facts rather than copying the full `non-default args` line.

Add a regression test if shared log sanitization is implemented in code.

Prometheus and vLLM must remain internal.

Do not expose ports to host/LAN merely to make benchmarking easier.

---

# PART 11 — Clean GEN-03C 512 control on vLLM 0.27.1

After Parts 1–10 are code-side clean, switch the real local `.env` to:

```env
VLLM_IMAGE=vllm/vllm-openai:v0.27.1
VLLM_USE_V2_MODEL_RUNNER=0
ANSWER_EVALUATION_MAX_TOKENS=512
```

Keep all other settings fixed.

Verify:

```text
effective image = v0.27.1
observed server version = 0.27.1
runner = V1
```

Perform the representative warmup.

Then run:

```text
Dataset: Smoke30
Profile: Smoke Quality
```

Save:

```text
gen03d_vllm0271_eval512_clean_smoke30.zip
```

## 512 decision evidence

For every failed `answer_evaluation`, the exported artifact must now show numeric:

```text
provider_finish_reason
application_status
parse_stage
input_tokens
output_tokens
max_tokens
total_tokens
latency_ms
```

### Truncation confirmed

Treat truncation as confirmed when a failed evaluator call shows:

```text
provider_finish_reason = length
application_status = structured_output_invalid
parse_stage = parse
max_tokens = 512
output_tokens approximately/equal to the provider-reported ceiling
```

Do not require every failure to be truncation before proceeding.

Classify failures into at least:

```text
length_truncation
normal_stop_parse_failure
validation_failure
provider_failure
other
```

Do not collapse them.

---

# PART 12 — Finish the evaluator budget sweep

If the clean 0.27.1 run confirms length truncation, perform a controlled sweep.

Only change:

```text
ANSWER_EVALUATION_MAX_TOKENS
```

## Candidate 640

```env
ANSWER_EVALUATION_MAX_TOKENS=640
```

Save:

```text
gen03d_vllm0271_eval640_smoke30.zip
```

If 640 produces:

```text
0 length-truncation failures
```

then 640 is the current preferred ceiling unless another reliability problem requires separate treatment.

Do **not** run 768 merely because it is listed.

## Candidate 768

Run only if 640 still has genuine `finish_reason=length` evaluator failures.

```env
ANSWER_EVALUATION_MAX_TOKENS=768
```

Save:

```text
gen03d_vllm0271_eval768_smoke30.zip
```

## Selection rule

Choose the **smallest** evaluator ceiling that eliminates genuine length truncation without material latency/reliability regression.

A `stop + parse failure` is **not** evidence that the ceiling is too small.

Do not choose 768 to hide a normal-stop malformed JSON problem.

Compare:

```text
structured_output_invalid total
length-truncation count
normal-stop parse-failure count
provider finish-reason distribution
output-token p50/p95/p99
answer_evaluation latency p50/p95
phase wall time
preemptions
queue/execution timing
quality denominators
```

---

# PART 13 — Conditional structured-output reliability experiment

Run this part **only if**, at the selected evaluator token ceiling, one or more evaluator calls still fail as:

```text
provider_finish_reason = stop
application_status = structured_output_invalid
parse_stage = parse
```

Do not raise the token ceiling to address this failure mode.

## Goal

Test whether provider-side JSON-schema constraints eliminate normal-stop malformed JSON without changing the evaluator rubric/schema.

vLLM's OpenAI-compatible Completions API supports structured-output constraints. Use the installed runtime's supported request contract; do not use deprecated guided-decoding fields.

Preferred current contract when supported:

```json
{
  "structured_outputs": {
    "json": {"...": "JSON schema"}
  }
}
```

Do not rely on a documentation assumption alone. Add a bounded runtime capability test / integration test against the actual server.

## Causal-isolation rule

Do **not** first introduce structured-output transport on 0.28 and compare it to legacy transport on 0.27.

First test the transport change on the **same vLLM version** used for the evaluator control:

```text
vLLM = 0.27.1
same selected evaluator budget
same model
same prompts
same schema
same concurrency
same everything else
```

Preferred implementation:

```text
legacy/current structured-output transport
vs
provider JSON-schema constrained transport
```

behind an explicit bounded configuration value, for example:

```text
VLLM_STRUCTURED_OUTPUT_MODE=legacy|json_schema
```

Use existing project naming conventions if a better field already exists.

Record the mode in benchmark provenance and strict compatibility semantics.

## Schema source

Do not hand-maintain a second evaluator schema.

Derive the provider JSON schema from the same typed output model used by the application's Pydantic validation when practical.

The application validator remains authoritative after provider generation.

Do not loosen validation.

Do not fabricate missing fields.

## Scope

Initially constrain only the existing typed structured actions that already require JSON and are compatible with this transport.

Do not change streaming `answer_generation` merely to broaden the experiment.

## Acceptance

Keep provider-side structured JSON only if it:

```text
eliminates/materially reduces normal-stop parse failures
introduces no provider/protocol errors
preserves application validation
preserves bounded telemetry
has acceptable latency
```

If the actual 0.27.1 server does not support the chosen constraint contract cleanly:

```text
report unsupported/incompatible
```

Do not force it.

If this transport is accepted, use the **same transport mode for both versions** in the subsequent version-only A/B.

Save the same-version transport experiment as:

```text
gen03d_vllm0271_structured_output_smoke30.zip
```

only if this conditional part is executed.

---

# PART 14 — GEN-03 safety validation

Only after evaluator reliability is clean enough that:

```text
0 unexplained evaluator parse failures
0 provider protocol failures
0 new timeouts
```

run:

```text
PromptInjection8
Unanswerable20
```

using the selected:

```text
ANSWER_EVALUATION_MAX_TOKENS
structured-output transport mode
```

Save:

```text
gen03d_prompt_injection8.zip
gen03d_unanswerable20.zip
```

Required:

```text
no new safety regression
no structured evaluator failures
no fabricated answer-quality values
no fake retrieval misses
no EvalEvidenceConsistencyError regression
```

Do not run Full240 yet.

---

# PART 15 — Establish the final clean vLLM 0.27.1 control

The final selected GEN-03 configuration becomes the version A/B control configuration.

Do not reset the evaluator ceiling to 512 merely because old VLLM-028 tasks listed 512.

For the version comparison, both versions must use the **same selected evaluator configuration**.

The 0.27.1 control may reuse the final clean Smoke30 from Parts 11–13 if and only if:

```text
warmup completed before benchmark start
no measured-window JIT warning
correct image/version proven
same final evaluator budget
same final structured-output transport mode
same fixed runtime settings
safe telemetry present
```

Otherwise run one final clean control and save:

```text
vllm0271_final_control_smoke30.zip
```

---

# PART 16 — Run the true vLLM 0.28.0-cu129 upgrade-only candidate

Change only the version/image experiment variable.

Set local `.env`:

```env
VLLM_IMAGE=vllm/vllm-openai:v0.28.0-cu129
VLLM_USE_V2_MODEL_RUNNER=0
```

Keep the final evaluator configuration from GEN-03D exactly the same as the control.

Keep:

```text
LLM_REQUEST_PREFETCH=4
VLLM_MAX_NUM_SEQS=4
VLLM_GPU_MEMORY_UTILIZATION=0.80
VLLM_MAX_MODEL_LEN=10240
prefix caching enabled
same model
same quantization
same corpus
same retrieval
same evaluator budget
same structured-output transport mode
```

Do not set/tune:

```text
max_num_batched_tokens
performance_mode
async scheduling
stream_interval
KV cache bytes
GDN backend
attention backend
linear backend
MTP
speculative decoding
```

Prove effective image with:

```powershell
docker compose config
```

Verify observed runtime:

```text
/version -> 0.28.0
runner -> V1
/v1/models contains served model
```

Run the same warmup sequence as control.

Then run:

```text
Dataset: Smoke30
Profile: Smoke Quality
```

Save:

```text
vllm0280_cu129_upgrade_only_smoke30.zip
```

If measured-window JIT occurs:

```text
mark contaminated
repeat once after warm state
```

Do not use contaminated timing as the final A/B result.

---

# PART 17 — Compare the final version A/B

Compare:

```text
vLLM 0.27.1 clean warmed control
vs
vLLM 0.28.0-cu129 clean warmed candidate
```

Both must use identical application/evaluator configuration.

## Required correctness/reliability dimensions

```text
30 items accounted
success / failed / guardrail / timeout counts
structured_output_invalid by finish reason
provider errors
protocol errors
OOM
EvalEvidenceConsistencyError
retrieval evidence consistency
answer-quality measured/unmeasured denominators
```

## Required performance dimensions

```text
phase wall time
queue_wait mean/p95
execution mean/p95
total_elapsed mean/p95

answer_generation latency p50/p95
answer_evaluation latency p50/p95
content_risk_scan latency p50/p95

TTFT
ITL
prompt token throughput/rate
generation token throughput/rate

preemptions
KV cache usage
KV cache size/capacity
running requests
waiting requests
prefix cache queries
prefix cache hits
```

## Required runtime/backend comparison

```text
configured image
observed server version
CUDA runtime
FlashInfer version
sampling backend
GDN prefill backend
GDN decode backend
attention backend
linear/quantization kernel
chunked prefill
prefix caching
max_num_batched_tokens observed/unobserved
performance_mode observed/unobserved
```

Do not guess missing values.

## Quality

Compare:

```text
MRR
Recall@5
Hit@1
groundedness
citation precision
citation recall
hallucination rate
unsupported claims
```

Always include denominators.

Do not attribute one stochastic quality movement to the vLLM version without repeated/deterministic evidence.

---

# PART 18 — Version decision thresholds

These are engineering decision rules, not statistical-significance claims.

## Clear win

If clean 0.28-cu129 is:

```text
>=10% faster wall time
```

with clean reliability:

```text
KEEP 0.28.0-cu129
```

## Neutral

If clean wall-time delta is within:

```text
±5%
```

performance is approximately neutral.

Keep 0.28-cu129 only if reliability is at least as good and the runtime/observability benefits justify it.

## Ambiguous

If delta is roughly:

```text
5–10%
```

in either direction:

repeat one warmed clean run per version.

## Regression

If 0.28-cu129 is repeatedly:

```text
>10% slower
```

or introduces:

```text
OOM
provider protocol failure
structured-output regression
startup instability
V2 activation
new deterministic correctness failure
```

then:

```text
ROLL BACK to 0.27.1
```

---

# PART 19 — Preemption/KV-cache interpretation and next task

Do not tune GPU memory during the version A/B.

But the latest diagnostic already showed:

```text
23 preemptions
~0.48 GiB KV cache
11,421 KV-cache tokens
~1.12x max concurrency at 10,240 tokens/request
```

The prior 0.27.1 diagnostic showed approximately:

```text
22 preemptions
~0.48 GiB KV cache
```

So a version-only upgrade has not yet demonstrated that it solves the capacity problem.

If the selected version still shows meaningful preemptions, the next experiment should be:

```text
VLLM_GPU_MEMORY_UTILIZATION
0.80
0.85
0.90
```

with everything else fixed.

Measure:

```text
preemptions
KV capacity/usage
waiting/running
TTFT
ITL
wall time
OOM/stability
```

Only after that should `max_num_batched_tokens` become the next scheduler sweep unless new evidence points elsewhere.

Proposed later matrix:

```text
unset/current auto
4096
8192
16384
```

Then, separately:

```text
performance_mode
```

Do not execute those tuning sweeps inside the version-only gate of this task.

---

# PART 20 — Validation policy

Follow repository policy:

> TEST WHAT CHANGED. LET CI TEST THE REPOSITORY.

At task start:

```powershell
python scripts/ai/check.py doctor
```

During coding:

```powershell
python scripts/ai/check.py focused <service> --files <changed> --tests <focused>
```

Near completion for affected services:

```powershell
python scripts/ai/check.py affected llm_agent
python scripts/ai/check.py affected rag
```

when supported and appropriate.

Run Ruff on changed Python files.

Run mypy only for changed typed code in normal CI scope.

Known pre-existing failures must be reported separately from new failures.

Do not claim them as caused by this task unless the changed code affects them.

Run:

```powershell
docker compose config
```

for both explicit local `.env` states:

```text
control   -> v0.27.1
candidate -> v0.28.0-cu129
```

CI remains authoritative after commit/push, but this task itself must not commit or push.

---

# Expected touched areas

Prefer the minimum required set.

Likely existing GEN-03C files:

```text
backend/shared/metrics.py
backend/llm_agent/app/services/llm_service.py
backend/llm_agent/app/schemas/llm.py
backend/llm_agent/app/messaging/llm_handler.py
backend/llm_agent/app/tests/test_provider_finish_reason.py
backend/llm_agent/app/tests/test_llm_service.py

backend/rag/app/services/conversation_kafka_utils.py
backend/rag/app/services/conversation_messages.py
backend/rag/app/services/conversation_graph.py
backend/rag/app/services/eval_runner.py
backend/rag/app/services/benchmark_summary.py
backend/rag/app/services/benchmark_export.py
backend/rag/app/services/benchmark_prometheus.py
backend/rag/app/tests/test_llm_action_evidence.py
```

Likely VLLM-028-01A files:

```text
docker-compose.yml
.env.example
docker/prometheus/prometheus.yml
scripts/vllm_warmup.py
tests/test_vllm_runtime_contract.py
backend/llm_agent/app/llm/implementations/vllm.py
backend/rag/app/services/benchmark_manifest.py
backend/rag/app/services/benchmark_comparison.py
backend/rag/app/services/benchmark_prometheus.py
backend/rag/app/services/benchmark_export.py
associated focused tests
```

If conditional structured-output transport is required, touch the minimum typed LLM interface/config/adapter files necessary.

Do not add a new framework.

Do not touch unrelated services.

Do not regenerate or commit benchmark ZIPs.

Local `.env` must be changed for operator runs but remain ignored/untracked.

---

# Out of scope

Do not implement in this task:

```text
Model Runner V2
VLLM_WSL2_ENABLE_PIN_MEMORY workaround
CUDA 13 candidate
MTP
speculative decoding
forced FlashInfer GDN
forced attention backend
forced linear backend
prefix caching ON/OFF experiment
max_num_batched_tokens tuning
performance_mode tuning
gpu_memory_utilization tuning during version A/B
stream_interval tuning
Qdrant upgrade
hybrid retrieval
CrossEncoder
RAG-01 pass2 ranking fix
RAG-02 retrieval parallelism
RAG-03 context redesign
SAFE-01 streaming safety redesign
Full240
large build-provenance redesign
answer-evaluation rubric redesign
answer-evaluation schema simplification
```

Provider-side JSON-schema constraint testing is allowed **only** under PART 13 and only if normal-stop parse failures remain after token truncation is handled.

---

# Acceptance criteria

```text
[ ] Existing GEN-03C provider/application status contracts are preserved.
[ ] GEN-03B error/retrieval-evidence invariants remain intact.
[ ] Safe numeric llm_action token evidence is no longer redacted.
[ ] Safe numeric vLLM token/KV/ITL metrics are no longer redacted.
[ ] Credential/token secrets remain redacted.
[ ] Per-failure evaluator evidence includes numeric output_tokens and max_tokens.
[ ] A clean warmed 0.27.1 evaluator run at 512 exists.
[ ] 512 failures are classified into truncation vs normal-stop parse vs other.
[ ] 640 is run only after truncation is confirmed.
[ ] 768 is run only if 640 still has genuine length truncation.
[ ] The smallest reliable evaluator ceiling is selected.
[ ] Normal-stop malformed JSON is not “fixed” by blindly raising max_tokens.
[ ] If normal-stop parse failure remains, structured-output transport is tested as a separate same-version experiment.
[ ] PromptInjection8 passes on the selected evaluator configuration.
[ ] Unanswerable20 passes on the selected evaluator configuration.
[ ] docker-compose candidate default is v0.28.0-cu129.
[ ] Local .env explicitly switches between control and candidate images.
[ ] Local .env remains ignored/untracked.
[ ] VLLM_USE_V2_MODEL_RUNNER remains 0 everywhere.
[ ] Warmup covers tiny, representative-prefill and concurrency shapes.
[ ] Benchmark-start time is after warmup completion.
[ ] Measured-window JIT contamination is detectable and invalidates timing.
[ ] /v1/models/{id} known-404 probe is removed.
[ ] /health readiness remains valid.
[ ] /v1/models served-model discovery remains valid.
[ ] /version is actually queried for observed server version when available.
[ ] Configured and observed vLLM provenance are semantically distinct.
[ ] GDN/attention/linear/sampling backend evidence is captured when observable.
[ ] Startup evidence is sanitized; exposed API key is rotated by operator.
[ ] Prometheus/vLLM remain internal.
[ ] A clean warmed 0.27.1 final control exists.
[ ] A clean warmed 0.28.0-cu129 candidate exists.
[ ] Version-only A/B changes no scheduler tuning variable.
[ ] Final report includes preemption/KV evidence.
[ ] Final keep/repeat/rollback decision follows the defined thresholds.
[ ] Full240 is not run.
```

---

# Required manual artifacts

Return the artifacts that were actually needed by the gates.

Minimum expected:

```text
gen03d_vllm0271_eval512_clean_smoke30.zip
```

If truncation confirmed:

```text
gen03d_vllm0271_eval640_smoke30.zip
```

Only if 640 still truncates:

```text
gen03d_vllm0271_eval768_smoke30.zip
```

Only if normal-stop malformed JSON requires PART 13:

```text
gen03d_vllm0271_structured_output_smoke30.zip
```

After reliability selection:

```text
gen03d_prompt_injection8.zip
gen03d_unanswerable20.zip
```

Version A/B:

```text
vllm0271_final_control_smoke30.zip
vllm0280_cu129_upgrade_only_smoke30.zip
```

If a final control can validly reuse an earlier clean selected-budget run, do not run an unnecessary duplicate; document the reuse explicitly.

Do not attach raw unsanitized vLLM startup logs.

---

# Final report — return exactly

1. Branch and working-tree status.
2. Changed tracked files grouped by:
   - GEN-03C telemetry/evidence;
   - sanitizer/export;
   - vLLM runtime/provenance;
   - warmup/readiness;
   - conditional structured-output transport if executed;
   - tests.
3. Confirmation local `.env` was changed during the experiment and remained ignored/untracked.
4. Sanitizer fix:
   - safe numeric fields now preserved;
   - secret regression tests.
5. Provider finish-reason/application-status contract.
6. Proof provider usage survives structured-output failure.
7. GEN-03B regression check.
8. Clean 0.27.1 / 512 diagnostic:
   - execution totals;
   - failed item IDs;
   - failure classes;
   - finish reasons;
   - exact output_tokens/max_tokens per failed evaluator;
   - evaluator p50/p95/p99 output tokens;
   - evaluator p50/p95 latency.
9. Truncation root-cause conclusion.
10. 640 result, if run.
11. 768 result, if run.
12. Selected evaluator budget and why it is the smallest correct choice.
13. Normal-stop malformed-JSON conclusion.
14. Structured-output constraint experiment result, if executed:
    - runtime support;
    - same-version A/B;
    - reliability/latency decision;
    - selected transport mode.
15. PromptInjection8 result.
16. Unanswerable20 result.
17. Candidate image/default changes.
18. Control and candidate effective-image proof from `docker compose config`.
19. Model Runner V1 proof for both versions.
20. `/health`, `/v1/models`, `/version` results for both versions.
21. Confirmation no `/v1/models/{id}` known-404 probe remains.
22. Warmup implementation and exact bounded shapes.
23. Warmup start/completion evidence for each measured run.
24. JIT contamination status for each final A/B run.
25. Configured vs observed provenance result.
26. Build-provenance status: trustworthy or incomplete.
27. 0.27.1 observed runtime:
    - server version;
    - CUDA;
    - FlashInfer;
    - sampling backend;
    - GDN prefill/decode;
    - attention backend;
    - linear kernel;
    - chunked prefill;
    - prefix caching.
28. 0.28.0-cu129 observed runtime with the same fields.
29. 0.27.1 final Smoke30 summary.
30. 0.28.0-cu129 final Smoke30 summary.
31. Wall-time / queue / execution / total-elapsed delta.
32. LLM action latency delta by request type.
33. TTFT / ITL / prompt throughput / generation throughput comparison.
34. Preemption / KV-cache / running-waiting comparison.
35. Prefix-cache comparison.
36. Reliability / provider finish-reason comparison.
37. Retrieval and quality comparison with denominators.
38. Focused/affected test counts.
39. Ruff result.
40. Mypy result or why not run.
41. `docker compose config` result.
42. CI status.
43. Security confirmation:
    - previously exposed VLLM API key rotated by operator or explicitly still pending;
    - no replacement key printed;
    - shared evidence sanitized.
44. Final version decision:
    - keep 0.28.0-cu129;
    - repeat due noise;
    - or rollback to 0.27.1.
45. Exact recommended next experiment:
    - GPU memory 0.80 / 0.85 / 0.90 if preemptions remain meaningful;
    - otherwise the next evidence-supported tuning variable.
46. Deferred items and remaining risks.

Do not commit or push.
