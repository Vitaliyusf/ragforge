# BMARK-15A — Benchmark accounting, per-item outcome export, and strict JSON evidence

**Branch:** `fix/benchmark-evidence-accounting`

## Goal

Fix correctness defects discovered by the Smoke30 and Full240 diagnostic ZIPs before any further benchmark claims are trusted.

This task is about **measurement correctness**, not RAG quality.

## Observed defects

Current diagnostic evidence has shown:

1. `reached` can exceed the dataset size because scoring counters and execution outcome counters are summed together.
2. Guardrail blocks are counted in benchmark progress/summary, but per-item export does not always identify the blocked item with explicit outcome/stage fields.
3. Prometheus snapshots may contain string values such as `"NaN"` even though unavailable evidence must be represented as `null`.
4. Summary/export must remain strict JSON and must not fabricate zeroes for unmeasured values.

## Required model: two independent axes

Do not mix scoring eligibility with execution outcome.

### Axis A — execution

For a phase with 240 items:

```text
total = 240

succeeded = 236
guardrail_blocked = 4
failed = 0
timed_out = 0
interrupted = 0

236 + 4 + 0 + 0 + 0 = 240
```

### Axis B — scoring

For the same phase:

```text
dataset_items = 240

scored = 220
skipped = 20
unscorable = 0

220 + 20 + 0 = 240
```

A blocked item may also be unanswerable/skipped for scoring. It must not be counted twice in a single denominator.

## Required changes

### 1. Replace ambiguous `reached`

Inspect the current summary schema and choose the smallest backward-compatible correction.

Preferred direction:

```text
execution:
  total
  succeeded
  guardrail_blocked
  failed
  timed_out
  interrupted

scoring:
  dataset_items
  scored
  skipped
  unscorable
```

If an existing field such as `items_evaluated` must remain for compatibility, preserve it but do not use it as an execution-outcome counter.

Do not keep a `reached` value whose arithmetic can exceed the actual phase item count.

If `reached` remains for compatibility, define it unambiguously and test the invariant:

```text
0 <= reached <= dataset_items
```

### 2. Per-item outcome export

Diagnostic `per-item.json` must expose, where available:

```text
outcome
guardrail_stage
timed_out
error_class
```

Use project-consistent field names.

For a guardrail block, the ZIP must let an analyst identify:

```text
item_id = ...
outcome = guardrail_blocked
guardrail_stage = input | output
```

Do not export raw sensitive prompt text just to explain a block.

### 3. Strict non-finite normalization

Sanitize non-finite Prometheus/sample values recursively.

At minimum normalize:

```text
NaN
"NaN"
+Inf
"+Inf"
-Inf
"-Inf"
Infinity
"Infinity"
-Infinity
"-Infinity"
```

to:

```json
null
```

Do this in the export/evidence normalization layer, not by silently changing the underlying Prometheus server semantics.

All generated JSON must remain valid under strict `allow_nan=False`.

### 4. Summary totals

Totals across phases must not double-count outcome/scoring axes.

If three phases each process 30 items, a pooled execution total may be 90 phase-item observations. It must not become 94 merely because four guardrail blocks are also part of scoring-skipped rows.

### 5. Backward compatibility

Existing benchmark/eval records lacking newer outcome fields must remain readable.

Normalize missing values honestly:

```text
missing -> null / unknown
```

Never infer a historical block/error type that was not stored.

## Non-goals

Do not:

- change retrieval ranking;
- change Pass2;
- change generation prompts;
- change vLLM settings;
- change benchmark concurrency;
- change guardrail policy;
- add new benchmark phases;
- implement provenance/comparison changes from BMARK-15C.

## Required tests

Add focused tests covering at least:

1. 30-item phase with 28 success + 2 blocked reports execution total 30.
2. 24 scored + 6 skipped remains scoring total 30 even if 2 skipped items were blocked.
3. Phase totals never exceed dataset item count on one execution axis.
4. Multi-phase pooled totals do not double-count guardrail blocks.
5. Guardrail-blocked per-item export includes explicit outcome.
6. Guardrail stage is exported when known.
7. Legacy per-item rows without outcome still export safely.
8. Float NaN becomes `null`.
9. String `"NaN"` becomes `null`.
10. `+Inf`, `-Inf`, `"Infinity"` variants become `null`.
11. ZIP JSON serializes with `allow_nan=False`.
12. Existing secret redaction remains intact.
13. Tenant-scoped export behavior remains unchanged.

## Validation policy

At task start:

```powershell
python scripts/ai/check.py doctor
```

Then run focused tests and Ruff only on changed Python files.

Because this changes benchmark summary/export contracts, run the RAG affected-service suite once near completion.

Run mypy only if changed typed contracts enter normal CI mypy scope.

GitHub CI remains the broad validation authority.

## Manual acceptance

Run **Smoke30 only**.

Verify:

```text
all 30 items accounted for
execution counters sum to 30
scoring counters sum to 30
guardrail-blocked items identifiable in per-item export
actual failures = 0 for healthy run
no NaN/Infinity strings in exported JSON
```

Do not run Full240 for this task.

## Final report

Return:

1. schema before/after;
2. exact double-counting bug fixed;
3. per-item export fields added;
4. non-finite normalization behavior;
5. focused/affected tests and counts;
6. manual Smoke30 checks still required;
7. known compatibility/deprecation notes.

Do not commit or push.
