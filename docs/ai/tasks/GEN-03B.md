# GEN-03B — Preserve retrieval evidence across graph failures and propagate the original pipeline error

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Branch:** `fix/e2e-graph-error-propagation`

## Goal

Fix the remaining end-to-end benchmark correctness failure exposed after GEN-03A.

After GEN-03A:

- safe `llm.max_tokens` provenance export is fixed;
- missing/inconsistent final-context evidence is no longer silently scored as a retrieval miss;
- however, several Smoke30 items still terminate with `EvalEvidenceConsistencyError` even after a full rebuild, clean data reset, and re-upload.

The current evidence strongly indicates that retrieval succeeds, but a later conversation-graph stage fails before `STAGE_FINAL_CONTEXT` is persisted. The graph then returns an error-shaped result with empty `sources`, while EvalRunner can lose the original graph failure and surface only the secondary evidence inconsistency.

This task must make the failure semantics truthful:

```text
retrieval succeeds
↓
final context becomes known
↓
later generation/evaluation stage fails
↓
original graph error is preserved
↓
retrieval evidence remains usable
↓
answer-quality scoring is unavailable
```

Do not turn downstream LLM/evaluator failures into fake retrieval misses.

---

# Incident evidence

Two post-GEN-03A Smoke30 runs were compared:

```text
gen03_smoke30.zip
gen03_smoke30_refreshed.zip
```

The second run was after:

```text
full system reset
new build
fresh upload of the benchmark corpus
fresh dataset/index identifiers
```

The same failure class still occurred.

Before refresh:

```text
q004
q011
q013
q016
q021
q239
```

After refresh:

```text
q004
q014
q018
q024
```

These rows showed:

```text
base retrieval stage present
valid retrieval candidates present
final_context stage missing
EvalEvidenceConsistencyError
```

The failure set changed between runs, which makes stale data/index corruption unlikely.

The refreshed corpus also reproduced nearly identical base retrieval ranking:

```text
23 / 24 answerable questions:
expected chunk at rank 1

1 / 24:
expected chunk at rank 2
```

Therefore do not investigate this task as a stale-Qdrant / stale-Mongo / corpus-upload problem unless new evidence proves otherwise.

---

# Strongly supported root-cause hypothesis

Current graph flow is approximately:

```python
final_state = await graph.ainvoke(state)

if retrieval_trace is not None:
    retrieval_trace.record_stage(
        STAGE_FINAL_CONTEXT,
        final_state.get("retrieved_chunks", []),
    )

result = self._build_result(final_state)
return result
```

But the graph-level exception branch returns approximately:

```python
result = {
    "answer": "",
    "sources": [],
    "review": {},
    "error": str(exc),
}
return result
```

This creates a failure window:

```text
retrieval already succeeded
↓
retrieved_chunks exists in graph state
↓
later node fails
↓
graph never reaches terminal final-context recording
↓
exception result returns sources=[]
↓
EvalRunner receives no final sources
↓
secondary evidence-consistency failure masks the original graph failure
```

This task must prove or reject that hypothesis and fix the actual source.

Do not assume `answer_evaluation` is the exact failing node until the original exception is preserved and inspected.

---

# PART 1 — Preserve the original graph failure contract

Any conversation-graph exception must return an explicit failed result.

Required minimum fields:

```text
outcome = failed
error
error_class
failed_node
```

Use repository conventions for names if an existing typed error/result contract exists.

Example conceptual result:

```json
{
  "outcome": "failed",
  "error": "Structured output validation failed ...",
  "error_class": "ValueError",
  "failed_node": "evaluate_answer",
  "answer": "",
  "sources": [...]
}
```

Do not return an exception result that can fall through to:

```python
result.get("outcome", "success")
```

as `success`.

The original exception remains the primary failure.

---

# PART 2 — Do not erase known retrieval sources on a later graph error

If retrieval/context selection already completed before the failing node, the exception result must preserve the last authoritative selected context.

Do not automatically return:

```text
sources = []
```

merely because generation/evaluation/persistence failed later.

Preferred rule:

```text
if final/selected retrieval context is already known:
    error result.sources = that known context
else:
    error result.sources = []
```

The context must come from trusted graph state.

Do not reconstruct it from an earlier benchmark trace.

Do not fall back to base retrieval simply to keep retrieval metrics high.

---

# PART 3 — Capture final-context evidence when the context becomes authoritative

Currently final context is recorded after the entire graph completes.

That is too late if later nodes can fail.

Move or add terminal-context recording at the point where the set of chunks used by answer generation becomes authoritative.

The invariant should be:

> once the graph has committed to the context that generation will use, that context is durable in the retrieval trace even if generation, evaluation, guardrails, revision, persistence, or later nodes fail.

Preferred ownership:

```text
retrieval/context-selection node
or
the boundary immediately before answer generation
```

rather than the outermost `ConversationGraph.run()` success-only tail.

Avoid recording multiple contradictory `final_context` stages.

If the context can legitimately change later, use the point after the last legitimate context mutation and before the first downstream stage that cannot change retrieval.

---

# PART 4 — Keep one source of truth

The following must agree when context is known:

```text
graph state retrieved_chunks
retrieval_trace final_context
result.sources
EvalRunner retrieved_ids
```

Do not maintain independent transformations that can drift.

Preferred data flow:

```text
authoritative selected chunks
        ├─→ retrieval_trace.final_context
        ├─→ result.sources
        └─→ EvalRunner final-context scoring
```

Filtering/normalization should be shared or contractually equivalent.

---

# PART 5 — Distinguish three failure timings

The system must distinguish:

## A. Failure before retrieval/context exists

Example:

```text
input guardrail failure
embedding failure
retrieval RPC failure
```

Expected:

```text
outcome = failed / guardrail_blocked as appropriate
retrieval evidence unavailable
retrieval scoring unavailable
answer quality unavailable
```

Do not fabricate sources.

## B. Failure after retrieval/context exists but before answer-quality completion

Example:

```text
generation error
answer evaluation parse error
output guardrail infrastructure error
```

Expected:

```text
outcome = failed
original error preserved
retrieval evidence valid
retrieval scoring allowed
answer-quality scoring unavailable
```

This is the key GEN-03B case.

## C. Normal successful completion

Expected existing behavior:

```text
outcome = success
retrieval evidence valid
retrieval scoring valid
answer-quality evidence valid when measured
```

---

# PART 6 — EvalRunner must not mask the original graph error

Inspect:

```text
EvalRunner._run_graph_item(...)
```

and the subsequent row consistency logic added in GEN-03A.

If `result` contains:

```text
outcome = failed
error = <original graph error>
```

then EvalRunner must preserve:

```text
row.error
row.error_class
row.outcome
failed_node if available
```

The secondary consistency checker must not replace this with:

```text
EvalEvidenceConsistencyError
```

unless there truly is an independent evidence-contract violation and no more primary error exists.

Priority:

```text
primary pipeline failure
    >
secondary evidence inconsistency
```

If both exist, preserve the primary failure and optionally add a bounded secondary diagnostic field/log.

---

# PART 7 — Retrieval scoring must survive downstream failures when evidence is valid

This task should use the execution/scoring separation already present in the benchmark.

For case B:

```text
execution outcome = failed
```

but if final retrieval context was already known:

```text
retrieval scoring = valid
```

The row may therefore legitimately have:

```text
outcome = failed
retrieved_ids = [...]
first_hit_rank = ...
reciprocal_rank = ...
retrieval scores = ...
answer-quality fields = null/unmeasured
```

Do not conflate:

```text
the answer pipeline failed
```

with:

```text
retrieval failed
```

This is critical for truthful aggregate retrieval metrics.

---

# PART 8 — Scoring denominators must remain explicit

Do not hide failed executions from accounting.

For a downstream failure with valid retrieval evidence:

Execution axis:

```text
failed += 1
```

Retrieval scoring axis:

```text
scored += 1
```

Answer-quality scoring:

```text
unavailable / skipped for that item
```

Use the existing summary schema if it already supports this distinction.

If answer-quality denominators are currently inferred from successful execution only, make the smallest change needed to keep them honest.

Do not invent zero quality scores for failed downstream calls.

---

# PART 9 — Guardrail semantics

Preserve the existing explicit guardrail behavior.

Input guardrail block:

```text
outcome = guardrail_blocked
guardrail_stage = input
```

Output guardrail behavior remains according to current code.

Do not turn guardrail blocks into generic failed graph errors.

If input guardrail occurs before retrieval, retrieval remains unmeasured.

If a post-retrieval guardrail intentionally returns no answer but retrieval evidence exists, preserve the known retrieval evidence according to current benchmark semantics.

Do not change safety policy in this task.

---

# PART 10 — Trace bound behavior

Retain the GEN-03A invariant:

```text
STAGE_FINAL_CONTEXT
```

must not be lost because normal diagnostic stage capacity was exhausted.

If GEN-03A already implemented reserved/final stage behavior, keep it.

Add/retain regression coverage proving:

```text
max trace stages reached
+
final context known
→ final_context still exported
```

Do not solve the runtime failure by merely increasing `eval_trace_max_stages`.

---

# PART 11 — Surface `failed_node`

The error evidence should make the actual failing stage visible.

Store/export a bounded field such as:

```text
failed_node
```

for failed end-to-end rows if the graph knows it.

Examples:

```text
generate_answer
evaluate_answer
output_guardrail
persist
```

Use actual internal node names; do not invent human-friendly names if the graph already tracks `runtime["current_node"]`.

Add `failed_node` to the diagnostic ZIP's per-item safe evidence allowlist.

Do not export prompt/answer/context text alongside it.

---

# PART 12 — Preserve original error classification

Where safe, preserve:

```text
error_class
```

from the underlying exception.

Examples:

```text
TimeoutError
ValueError
ValidationError
...
```

Do not expose stack traces or secrets in the ZIP.

Sanitize/truncate message text through the existing export path.

The point is to tell:

```text
structured-output failure
timeout
RPC failure
unexpected graph exception
```

apart.

---

# PART 13 — Focused deterministic tests

Add tests for at least the following.

## 1. Failure before retrieval

Graph fails before context exists.

Expected:

```text
outcome=failed
sources=[]
no final_context
retrieval unmeasured
original error preserved
```

## 2. Failure after final context, during generation

Context contains known chunk IDs.

Generation raises.

Expected:

```text
outcome=failed
failed_node identifies generation
sources preserve final context
retrieval_trace.final_context present
EvalRunner retrieved_ids present
retrieval metrics scored
answer-quality unmeasured
```

## 3. Failure during answer evaluation

Generation succeeds.
Answer evaluation raises or returns structured-output failure.

Expected same preservation behavior.

This is especially important because current benchmark telemetry showed nonzero `answer_evaluation` error rate during the incident.

## 4. Normal success

No regression to current successful path.

## 5. Input guardrail block

No fabricated retrieval evidence.

## 6. Legitimately empty context

Context-selection succeeds with empty context.

Later graph execution behaves according to existing semantics.

The trace must contain an explicit empty final-context stage rather than "missing".

## 7. Original error beats consistency error

Graph result carries a real pipeline failure plus incomplete evidence.

EvalRunner preserves the primary graph failure instead of replacing it with `EvalEvidenceConsistencyError`.

## 8. Valid retrieval scoring on failed execution

A failed downstream execution with known final context still contributes correct:

```text
first_hit_rank
MRR component
Recall@k
```

without contributing fabricated answer-quality scores.

---

# PART 14 — Aggregate regression tests

Construct a small dataset with mixed outcomes:

```text
item 1 success
item 2 post-retrieval evaluation failure
item 3 pre-retrieval failure
item 4 guardrail block
```

Assert independently:

```text
execution totals
retrieval scoring denominator
answer-quality scoring denominator
guardrail count
failed count
```

The important assertion:

> post-retrieval failure can count as execution failure while still contributing valid retrieval evidence.

Do not reintroduce execution/scoring double-counting.

---

# PART 15 — Diagnostic export

Ensure exported per-item evidence includes, when available:

```text
outcome
error
error_class
failed_node
guardrail_stage
retrieved_ids
first_hit_rank
retrieval_trace
retrieval scores
answer-quality fields
```

Do not include:

```text
raw answer
query text
raw context text
prompt
stack trace
credentials
```

Preserve strict JSON / NaN normalization.

---

# PART 16 — Keep GEN-03 candidate fixed

Do not change:

```text
ANSWER_GENERATION_MAX_TOKENS=128
ANSWER_EVALUATION_MAX_TOKENS=512
CONTENT_RISK_SCAN_MAX_TOKENS=128
QUERY_REWRITE_MAX_TOKENS=128
MEMORY_EXTRACTION_MAX_TOKENS=512

primary LLM prefetch=4
VLLM_MAX_NUM_SEQS=4
```

Do not change:

```text
temperature
top_p
prompts
retrieval settings
embedding
chunking
eval concurrency
```

The goal is to repair failure semantics under the same candidate.

---

# PART 17 — Validation policy

Follow:

```text
TEST WHAT CHANGED.
LET CI TEST THE REPOSITORY.
```

At task start:

```powershell
python scripts/ai/check.py doctor
```

Run focused tests while coding.

Expected touched areas:

```text
conversation_graph.py
eval_runner.py
retrieval_trace.py if necessary
benchmark export
benchmark summary/accounting if necessary
tests
```

Because this changes graph lifecycle/error semantics and benchmark accounting:

```text
python scripts/ai/check.py affected rag
```

is required once near completion.

Run Ruff on changed Python files.

Run mypy only if touched typed contracts are in normal CI scope.

Do not run the whole repository locally solely for completeness.

GitHub CI remains authoritative.

---

# PART 18 — Manual acceptance after merge

After merge:

```powershell
git switch main
git pull
```

Rebuild/recreate:

```text
rag
```

and any service whose code was actually changed.

Do **not** re-upload the corpus again for the first validation.

The refreshed corpus already proved that rebuilding/reindexing does not remove the issue.

---

# PART 19 — Smoke30 manual run

Run:

```text
Dataset: Smoke30
Profile: Smoke Quality
```

with fixed GEN candidate:

```text
prefetch = 4
max_num_seqs = 4
budgets = 128 / 512 / 128 / 128 / 512
```

Download:

```text
gen03b_smoke30.zip
```

---

# PART 20 — Manual ZIP acceptance

Primary acceptance:

```text
EvalEvidenceConsistencyError count = 0
```

unless a new truly independent evidence bug exists and is explicitly demonstrated.

Inspect the previously unstable IDs if present:

```text
q004
q011
q013
q014
q016
q018
q021
q024
q239
```

Do not require a particular item to succeed; LLM downstream behavior can be stochastic.

Instead require:

### If item succeeds

```text
final_context coherent
retrieved_ids coherent
normal scoring
```

### If item fails after retrieval

```text
original error preserved
failed_node present
final_context preserved
retrieved_ids preserved
retrieval scoring still valid
answer-quality unmeasured
```

### If item fails before retrieval

```text
retrieval unmeasured
no fabricated final context
```

Also verify:

```text
30 execution items accounted
no silent timeouts
strict JSON
no NaN/Infinity
token budgets still 128/512/128/128/512
```

---

# PART 21 — Compare against the two prior runs

Use:

```text
gen03_smoke30.zip
gen03_smoke30_refreshed.zip
gen03b_smoke30.zip
```

Compare:

```text
EvalEvidenceConsistencyError count
underlying graph error classes
failed_node distribution
retrieval MRR/Recall denominator
answer-quality denominator
phase wall time
LLM action error rates
```

Do not expect exact quality equality because generation/judge behavior is stochastic.

The key improvement is **truthful attribution**, not a particular MRR number.

---

# PART 22 — Gate back into GEN-03

If GEN-03B passes:

Proceed to the pending GEN-03 safety validation:

```text
PromptInjection8
Unanswerable20
```

Do not run Full240 yet.

Do not run another full rebuild unless a new infrastructure symptom appears.

---

# Out of scope

Do not implement:

- answer-evaluation 512 vs 640/768 experiment;
- memory-extraction budget tuning;
- retrieval ranking changes;
- pass-two ranking fix;
- hybrid retrieval;
- CrossEncoder;
- prompt changes;
- SAFE-01;
- new evaluator schemas;
- retry policy tuning;
- LLM queue prefetch tuning;
- vLLM concurrency tuning;
- broad graph refactor.

---

# Acceptance criteria

```text
[ ] Graph exceptions explicitly return outcome=failed.
[ ] Original error is preserved.
[ ] failed_node is preserved/exported.
[ ] Known final retrieval context survives downstream graph failures.
[ ] Final-context trace is recorded before later failure can erase it.
[ ] result.sources and trace final_context share authoritative state.
[ ] EvalRunner does not mask primary graph errors with EvalEvidenceConsistencyError.
[ ] Post-retrieval execution failures can still contribute valid retrieval metrics.
[ ] Answer-quality metrics remain unmeasured for failed downstream evaluation.
[ ] Pre-retrieval failures do not fabricate retrieval evidence.
[ ] Guardrail semantics remain unchanged.
[ ] Execution/scoring accounting remains independent and correct.
[ ] Focused tests pass.
[ ] affected rag validation passes.
[ ] CI passes.
[ ] Smoke30 shows truthful per-item failure attribution.
```

---

# Final report

Return exactly:

1. Proven root cause.
2. Exact failing graph node(s) reproduced in tests/manual evidence.
3. Why the previous graph error became `EvalEvidenceConsistencyError`.
4. Changed files grouped by:
   - graph lifecycle/error propagation
   - retrieval trace/final context
   - EvalRunner/scoring
   - benchmark summary/export
   - tests
5. New graph result error contract.
6. Final-context capture point and invariant.
7. Behavior for:
   - pre-retrieval failure
   - post-retrieval failure
   - guardrail block
   - successful completion
8. Execution vs retrieval-scoring vs answer-quality accounting.
9. Focused test counts.
10. affected RAG validation.
11. Ruff/mypy result if applicable.
12. CI result.
13. Manual Smoke30 still required.
14. Known deferred items.

Do not commit or push.
