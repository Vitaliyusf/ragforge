# GEN-03A — Fix E2E retrieval-evidence loss and safe max-token provenance export

**Branch:** `fix/e2e-retrieval-evidence-and-token-provenance`

## Goal

Fix two correctness issues exposed by the first real GEN-03 candidate run:

1. **P0 — End-to-end benchmark evidence can report `retrieved_ids=[]` / missing `final_context` even though the graph's retrieval trace contains valid candidates, including the expected chunk at rank 1.**
2. **P1 — Safe numeric per-action `llm.max_tokens` provenance is exported as `"[redacted]"` because the generic secret sanitizer sees the word `token`.**

This is a correctness/evidence task.

Do **not** tune token budgets, concurrency, retrieval, prompts, or quality behavior in this task.

---

# Incident evidence

The GEN-03 candidate actually ran with:

```text
answer_generation   = 128
answer_evaluation   = 512
content_risk_scan   = 128
query_rewrite       = 128
memory_extraction   = 512

primary LLM prefetch = 4
VLLM_MAX_NUM_SEQS    = 4
```

The benchmark itself was operationally healthy:

```text
30 items
28 success
2 guardrail_blocked
0 failed
0 timeout
```

However, 8 answerable items showed an inconsistent evidence state:

```text
q004
q006
q008
q011
q014
q016
q017
q024
```

For these items, diagnostic evidence showed approximately:

```text
outcome = success
error = null

retrieval_trace.base:
  expected golden chunk present
  expected chunk often rank 1
  candidates present

but:

retrieved_ids = []
first_hit_rank = null
final_context stage = missing
```

This caused aggregate retrieval metrics to fall to roughly:

```text
MRR      ≈ 0.646
Recall@5 ≈ 0.667
```

even though the base retrieval evidence for those rows showed the expected chunk had in fact been retrieved.

This must be diagnosed and fixed before more GEN-03 safety datasets are run.

---

# Important semantic rule

Do **not** "fix" the benchmark by scoring the base retrieval stage when the end-to-end graph actually used a different final context.

End-to-end retrieval metrics must continue to describe:

> **the chunks the conversation graph actually selected as final answer context**

not:

> "whatever appeared in an earlier retrieval stage."

If the graph intentionally drops every candidate, that can legitimately produce:

```text
final_context = []
retrieved_ids = []
```

but the evidence must explicitly show **why**.

The bug is the unexplained/inconsistent loss of final-context evidence, not simply the existence of an empty context.

---

# PART 1 — Reproduce the evidence-loss condition deterministically

Before changing behavior, add a focused test that reproduces the inconsistency.

Construct or reuse an end-to-end graph fixture where:

```text
base retrieval contains known chunks
graph execution succeeds
expected chunk is present in an earlier retrieval stage
```

and exercise the same path used by:

```text
EvalRunner._run_graph_item(...)
```

Capture:

```text
result["sources"]
RetrievalTrace.stages
final_state["retrieved_chunks"] if available at the graph boundary
row["retrieved_ids"]
row["outcome"]
```

The test should fail on the current buggy condition if it can be reproduced.

Do not write a test that merely asserts the desired output without exercising the real graph/eval boundary.

---

# PART 2 — Trace the source of truth through the graph

Inspect the actual end-to-end path:

```text
EvalRunner
  → ConversationGraph.run(...)
  → retrieval nodes / pass selection
  → final state
  → ConversationGraph._build_result(...)
  → result["sources"]
  → EvalRunner._run_graph_item(...)
  → retrieved_ids(...)
  → benchmark row
```

Current important contracts include:

```text
ConversationGraph.run:
  final_state["retrieved_chunks"]
  → retrieval_trace.record_stage(STAGE_FINAL_CONTEXT, ...)
  → _build_result(final_state)

ConversationGraph._build_result:
  "sources": state.get("retrieved_chunks", [])

EvalRunner._run_graph_item:
  result = graph_runner.run(...)
  ...
  return retrieved_ids(
      eligible_chunks({"chunks": result.get("sources") or []}),
      item_mode,
  )
```

Determine exactly where the final chunks disappear.

Possible classes of root cause to investigate include, but are not limited to:

- a node accidentally overwriting/clearing `retrieved_chunks`;
- branch/merge behavior losing state;
- regular vs extended graph state reducer semantics;
- result construction seeing a different state than retrieval tracing;
- final-context trace not being recorded because stage bounds are exhausted;
- a successful answer path returning before final context is persisted;
- post-retrieval policy filtering eliminating sources without recording the decision;
- schema/shape mismatch causing `eligible_chunks(...)` to reject/lose returned source objects.

Do **not** assume which one is correct before tracing it.

---

# PART 3 — Final-context trace must be reliable

For a completed graph run, `STAGE_FINAL_CONTEXT` is special: it describes what generation actually used.

It must not disappear merely because earlier diagnostic stages filled the generic trace bound.

Inspect:

```text
RetrievalTrace.record_stage(...)
max_stages
STAGE_FINAL_CONTEXT
```

Current behavior rejects any new stage once:

```text
len(self.stages) >= max_stages
```

If this can cause `STAGE_FINAL_CONTEXT` to be omitted, fix the trace semantics so final context is retained.

Preferred invariant:

```text
final_context is reserved / guaranteed for a completed graph run
```

Possible safe implementation strategies:

- reserve one stage slot for `STAGE_FINAL_CONTEXT`; or
- if the bound is already full, replace/drop the least-important earlier diagnostic stage and set `truncated=true`; or
- store final context separately and serialize it as a mandatory terminal stage.

Do not increase the trace bound blindly as the primary fix.

Do not silently discard the final context.

A truncated trace should say:

```text
truncated = true
```

while still preserving the terminal context evidence.

---

# PART 4 — Result sources and final-context evidence must agree

For a normal successful graph completion:

```text
result["sources"]
```

and:

```text
retrieval_trace.final_context
```

must represent the same final selected chunks, subject only to trace-size/candidate-view bounds.

Required invariant:

```text
IDs(result["sources"])
==
IDs(full final_state["retrieved_chunks"])
```

and the bounded trace view must be a prefix/bounded representation of that same final set.

Do not maintain two independent transformations that can drift.

Prefer deriving both from the same final-state value.

---

# PART 5 — Preserve legitimate empty-context behavior

An empty final context is not automatically an error.

Examples may include:

```text
unanswerable query
all retrieved chunks filtered by policy
retrieval returns no candidates
explicit graph branch decides no context is safe/useful
```

When final context is legitimately empty:

```text
STAGE_FINAL_CONTEXT must still exist
kept_count = 0
candidates = []
```

and, when a decision/filter caused it:

```text
retrieval_trace.decisions / dropped evidence
```

must explain the transition where possible.

Do not backfill `retrieved_ids` from `STAGE_BASE`.

Do not manufacture a retrieval hit.

---

# PART 6 — Successful answerable rows cannot lose unexplained source evidence

Add an explicit consistency check at the eval/graph boundary.

For an end-to-end item, distinguish:

```text
A. final_context recorded and non-empty
B. final_context recorded and intentionally empty
C. final_context missing unexpectedly
```

Case C is an instrumentation/correctness failure.

Do not silently score it as a retrieval miss.

Preferred behavior for C:

```text
row outcome / evidence status explicitly indicates internal evidence inconsistency
```

using the existing error/outcome model if appropriate.

At minimum:

- log it clearly;
- do not pretend `[]` is a measured final-context result;
- ensure aggregate retrieval metrics do not silently interpret missing evidence as a genuine miss.

Use the smallest change consistent with the current execution/scoring accounting model.

Do not convert all empty contexts into errors.

---

# PART 7 — Scoring semantics

For valid end-to-end rows:

```text
row["retrieved_ids"]
```

must be derived from the graph's final selected sources.

Then:

```text
first_hit_rank
reciprocal_rank
recall_at_k
precision_at_k
hit_rate_at_k
nDCG
```

must score those final-context IDs.

Do not score from:

```text
base stage
pass-one stage
union of all trace stages
```

unless that stage is actually the final graph context.

This preserves the existing benchmark definition.

---

# PART 8 — Add evidence-consistency tests for the observed pattern

Required tests should cover at least:

### A. Normal successful answerable item

```text
base contains expected chunk
final context contains expected chunk
result.sources contains expected chunk
retrieved_ids contains expected chunk
metrics score hit
```

### B. Final context changes ranking

```text
base order != final context order
```

Scoring must follow final context, proving no fallback to base.

### C. Legitimately empty final context

```text
base candidates exist
graph intentionally filters/selects none
final_context stage exists with 0 candidates
retrieved_ids=[]
```

This remains a real miss/empty context, not fabricated success.

### D. Trace stage bound reached

Fill the trace with enough earlier stages to reach/exceed the configured diagnostic bound.

Then complete the graph.

Required:

```text
final_context still present
truncated=true if earlier detail had to be dropped
```

### E. Unexpected missing final context

Inject a malformed/fake graph result that claims success but provides no final-context evidence.

Required:

```text
not silently scored as an ordinary empty retrieval result
```

---

# PART 9 — Fix safe `llm.max_tokens` provenance redaction

The benchmark export sanitizer currently has secret-key protection similar to:

```text
if key contains token:
    redact
```

with a narrow allowlist for known numeric token *metrics*.

The new provenance shape contains a safe mapping:

```json
"llm": {
  "max_tokens": {
    "answer_generation": 128,
    "answer_evaluation": 512,
    "content_risk_scan": 128,
    "query_rewrite": 128,
    "memory_extraction": 512
  }
}
```

This is configuration evidence, not a credential.

Current output incorrectly becomes:

```json
"max_tokens": "[redacted]"
```

Fix this without weakening credential protection.

---

# PART 10 — Redaction implementation requirements

Preferred approach:

Use a **path-aware exact safe allowlist** for this specific bounded provenance object, e.g. the known paths corresponding to:

```text
manifest.llm.max_tokens
runtime.llm.max_tokens
```

or whatever exact export paths exist.

The safe exception must apply only when:

```text
value is a mapping
keys are exactly/only known request types
values are finite integers/numbers or null
```

Known allowed child keys:

```text
answer_generation
answer_evaluation
content_risk_scan
query_rewrite
memory_extraction
```

Do not globally whitelist every field named `max_tokens`.

Do not globally decide that keys containing `token` are safe.

The following must remain redacted:

```text
access_token
refresh_token
auth_token
bearer_token
api_token
session_token
private_token
```

and any existing secret-like key patterns.

---

# PART 11 — Strict token-provenance validation

When exporting the safe `max_tokens` map:

- unknown child keys must not bypass redaction accidentally;
- strings containing arbitrary text are not valid safe numeric provenance;
- non-finite numbers normalize to null according to existing export rules;
- booleans should not be accepted as token counts if the sanitizer/type checks distinguish them;
- negative values should never appear from valid config, but export must not leak arbitrary payloads because of the safe path.

Prefer a helper such as:

```text
_is_safe_token_budget_provenance(path, value)
```

with explicit structure validation.

---

# PART 12 — Export tests

Required:

1. `manifest.llm.max_tokens` safe map survives export.
2. `runtime.llm.max_tokens` safe map survives export if present.
3. each five action values remains numeric.
4. `access_token` remains redacted.
5. `refresh_token` remains redacted.
6. arbitrary `"some_token": "secret-value"` remains redacted.
7. unrelated `max_tokens` at an unapproved path does not receive the safe exception.
8. malformed safe-path mapping with unknown/string payload does not broadly bypass redaction.
9. NaN/Infinity normalization remains intact.
10. strict JSON `allow_nan=False` remains intact.
11. historical exports without `max_tokens` remain valid.

---

# PART 13 — Comparison compatibility

Preserve the GEN-03 requirement that per-action budgets are meaningful provenance.

If the current comparison layer already treats the five token budgets as critical compatibility fields, keep that behavior.

If it does not, add explicit compatibility checks for:

```text
llm.max_tokens.answer_generation
llm.max_tokens.answer_evaluation
llm.max_tokens.content_risk_scan
llm.max_tokens.query_rewrite
llm.max_tokens.memory_extraction
```

Rules:

```text
known same      → same
known different → different / incompatible
missing         → unknown
```

Do not treat the redacted export string as provenance internally.

Comparison must operate on the stored unsanitized trusted benchmark document, while export sanitization only affects the downloadable artifact.

---

# PART 14 — Logging / observability

Add concise bounded logging for an unexpected evidence inconsistency.

Useful fields:

```text
benchmark_id
run_id
item_id
pipeline_mode
trace_stage_names
final_source_count
outcome
```

Do not log:

```text
query text
answer text
document text
context text
tokens/secrets
```

If the graph legitimately yields zero final sources, do not log it as an error solely because it is zero.

---

# PART 15 — Do not change GEN-03 candidate budgets

Keep:

```text
ANSWER_GENERATION_MAX_TOKENS=128
ANSWER_EVALUATION_MAX_TOKENS=512
CONTENT_RISK_SCAN_MAX_TOKENS=128
QUERY_REWRITE_MAX_TOKENS=128
MEMORY_EXTRACTION_MAX_TOKENS=512
```

Also keep:

```text
primary LLM prefetch = 4
VLLM_MAX_NUM_SEQS = 4
```

Do not tune anything in this PR.

---

# PART 16 — Tests / validation policy

Follow:

```text
TEST WHAT CHANGED.
LET CI TEST THE REPOSITORY.
```

At task start:

```powershell
python scripts/ai/check.py doctor
```

Run focused tests during coding.

Expected touched areas:

```text
rag conversation graph / retrieval trace
rag eval runner
benchmark export
benchmark comparison if required
tests
```

Run Ruff on changed Python files.

Run mypy only if touched typed contracts are in normal CI scope.

Because this crosses graph → eval → persisted benchmark evidence, run:

```text
python scripts/ai/check.py affected rag
```

once near completion.

Do not run the full local repository merely for completeness.

GitHub CI remains authoritative.

---

# PART 17 — Manual acceptance after merge

After CI green and merge:

```powershell
git switch main
git pull
```

Rebuild/recreate affected runtime services.

At minimum:

```text
rag
```

Recreate other services only if their code/config actually changed.

Do not re-upload the 56 core corpus files.

---

# PART 18 — Manual Smoke30 verification

Run exactly:

```text
Dataset: Smoke30
Profile: Smoke Quality
```

with fixed GEN settings:

```text
prefetch = 4
max_num_seqs = 4

answer_generation   = 128
answer_evaluation   = 512
content_risk_scan   = 128
query_rewrite       = 128
memory_extraction   = 512
```

Download:

```text
gen03a_smoke30.zip
```

---

# PART 19 — Manual ZIP acceptance

Check:

## Run health

```text
30 items accounted
0 unexpected failures
0 timeouts
expected guardrail blocks explicit
```

## Retrieval evidence

For every normal successful answerable row:

- `retrieval_trace.final_context` is present;
- `retrieved_ids` reflects the final context;
- a bounded/truncated trace still keeps final context;
- there is no unexplained `base hit → final_context missing → retrieved_ids=[]` state.

Specifically inspect the previously affected item IDs if still present in Smoke30:

```text
q004
q006
q008
q011
q014
q016
q017
q024
```

Do **not** require them all to be hits if the final graph genuinely changes context.

Require the evidence chain to be internally coherent.

## Aggregate retrieval metrics

Do not hardcode an expected exact MRR/Recall result.

Instead verify:

```text
aggregate metrics are derivable from the exported per-item final-context scoring evidence
```

and are no longer depressed by missing evidence masquerading as misses.

## Token provenance

The ZIP must visibly contain:

```text
answer_generation   128
answer_evaluation   512
content_risk_scan   128
query_rewrite       128
memory_extraction   512
```

under the intended provenance structure.

It must **not** show:

```text
"max_tokens": "[redacted]"
```

## Security

Verify representative credential-like fields are still redacted.

## JSON integrity

```text
no NaN
no Infinity
strict JSON parses
```

---

# PART 20 — Gate back into GEN-03

If `gen03a_smoke30.zip` passes:

```text
GEN-03A = PASS
```

Then continue the existing GEN-03 safety validation:

```text
PromptInjection8
Unanswerable20
```

Do not run another all-512 baseline.

Do not run Full240 yet.

---

# Out of scope

Do not implement:

- new retrieval algorithm;
- pass-two ranking fix;
- hybrid retrieval;
- CrossEncoder;
- token-budget retuning;
- answer-evaluation 512 vs 640/768;
- memory-extraction budget tuning;
- LLM prefetch changes;
- vLLM concurrency changes;
- prompt changes;
- SAFE-01;
- benchmark systemic dependency fail-fast;
- broad sanitizer redesign.

---

# Acceptance criteria

```text
[ ] Root cause of lost E2E final-context evidence is identified.
[ ] Final context cannot be silently dropped by trace stage bounds.
[ ] result.sources and final graph context share one source of truth.
[ ] Legitimate empty final contexts remain representable.
[ ] Missing evidence is not silently scored as a genuine retrieval miss.
[ ] End-to-end scoring still uses final context, never base-stage fallback.
[ ] Focused tests cover normal, reordered, empty, truncated, and inconsistent cases.
[ ] Safe llm.max_tokens provenance survives export.
[ ] Credential token fields remain redacted.
[ ] Token-budget compatibility semantics remain correct.
[ ] Strict JSON behavior remains correct.
[ ] Focused tests pass.
[ ] affected rag validation passes.
[ ] CI passes.
[ ] Smoke30 manual acceptance passes.
```

---

# Final report

Return exactly:

1. Root cause of the E2E source/final-context evidence loss.
2. Why the observed rows could show a base hit but empty `retrieved_ids`.
3. Changed files grouped by:
   - conversation graph / retrieval trace
   - eval runner/scoring
   - benchmark export
   - comparison/provenance
   - tests
4. Final-context invariant after the fix.
5. Legitimate empty-context behavior.
6. How missing evidence is handled.
7. Safe `max_tokens` redaction exception and why it does not weaken credential protection.
8. Focused test counts.
9. affected RAG validation result.
10. Ruff/mypy result if applicable.
11. CI result.
12. Manual Smoke30 still required.
13. Known deferred items.

Do not commit or push.
