# MEMORY-EVAL-01 — Build a labelled Memory V2 / Memory Agent evaluation suite

**Order:** 35  
**Phase:** 5 Memory V2  
**Priority:** P1  
**Branch:** `feat/memory-eval-suite`  
**Depends on:** `MEMORY-AGENT-01`

## Goal

Build a deterministic, labelled evaluation suite that measures whether Memory V2 stores the right information, avoids the wrong information, retrieves the right memory later, handles temporal updates/conflicts, and never leaks across users or tenants.

This task turns memory from a feature with tests into a capability with measurable evidence.

## Primary scope

- synthetic memory scenario dataset
- extraction/action labels
- retrieval labels
- lifecycle labels
- temporal/conflict labels
- isolation labels
- metrics
- benchmark runner/export
- reproducibility/provenance

## Required dataset

Create a deterministic synthetic benchmark containing at least:

500 scenarios

Prefer 750–1,000 if runtime remains inexpensive.

Scenario families must include:

- durable preferences
- project/work context
- stable entity facts
- irrelevant chatter
- temporary plans
- exact duplicates
- semantic duplicates
- corrections
- temporal updates
- scope-specific updates
- contradictions
- stale memories
- deletion requests
- multi-turn references
- Hebrew
- English
- mixed Hebrew/English
- cross-language retrieval
- tenant collisions
- user collisions
- adversarial attempts to access another user's memory

All data must be synthetic.

## Ground truth

Each scenario should declare, as applicable:

- scenario_id
- tenant_id
- user_id
- turns/input
- expected candidate memories
- expected action: ignore/create/update/supersede/merge/delete/etc.
- expected active memories after scenario
- expected inactive/superseded memories
- later retrieval queries
- expected retrieved memory IDs/facts
- forbidden memory IDs
- expected abstention/no-memory result
- language
- tags
- difficulty

Do not derive labels from the system output.

Ground truth must be authored by the deterministic scenario generator.

## Core metrics

### Memory creation/action quality

Report:

- candidate precision
- candidate recall
- create precision/recall
- no-op/ignore precision/recall
- update/supersede correctness
- duplicate suppression accuracy
- destructive-action false-positive count

### Memory retrieval quality

Report:

- Hit@1
- Recall@1
- Recall@3
- Recall@5
- MRR
- nDCG where labels support it
- irrelevant-memory rate
- stale-memory retrieval rate

### Lifecycle quality

Report:

- supersession correctness
- temporal-current-fact accuracy
- contradiction handling accuracy
- deletion correctness
- resurrection-after-delete count

### Isolation/security

Report:

- cross-tenant leakage
- cross-user leakage
- forbidden-memory retrieval count

Any leakage is a critical failure.

### Operational metrics

Report where available:

- memory extraction LLM latency
- retrieval latency
- persistence/update latency
- token usage
- structured-output failures
- retries/fallbacks
- benchmark wall time

## Splits

Create stable deterministic splits:

- smoke: 30–50 scenarios
- quick: ~100
- standard: ~250
- full: all scenarios

Diagnostic subsets:

- preference
- duplicate
- temporal
- conflict
- deletion
- Hebrew
- cross-language
- tenant-isolation
- user-isolation
- adversarial
- no-memory

## Important evaluation rules

- Never count evaluator/parser failures as memory correctness failures without separate attribution.
- Show denominators.
- Keep generation/action accuracy separate from retrieval accuracy.
- Keep leakage/security failures separate and explicit.
- Do not tune prompts/models against the full test set after seeing results.
- If tuning becomes necessary, create a train/dev split and preserve a held-out test set.

## Reproducibility

Record:

- dataset version/hash
- seed
- Git/source fingerprint where available
- embedding model/version
- vector collection/index
- LLM model/runtime
- prompt versions
- schema versions
- concurrency
- hardware/runtime

## Validation

Required:

- dataset schema tests
- deterministic generation/hash tests
- benchmark runner tests
- metric calculation tests
- security/leakage assertions
- export/provenance tests
- affected memory suite
- Ruff
- canonical mypy if applicable
- Compose/build if runtime changed
- diff-check

## Final artifacts

Produce benchmark artifacts using repository conventions where possible.

At minimum:

- dataset manifest
- scenario/query labels
- benchmark summary
- per-scenario diagnostics
- errors/failure attribution
- provenance/runtime manifest
- export archive

## Final report

Return:

### MEMORY-EVAL-01 CLOSEOUT

Dataset:
- scenarios
- languages
- categories
- dataset version/hash

Action quality:
- candidate precision/recall
- create precision/recall
- ignore/no-op correctness
- update/supersede correctness
- duplicate suppression
- unsafe destructive actions

Retrieval:
- Hit@1
- Recall@1
- Recall@3
- Recall@5
- MRR
- nDCG
- irrelevant-memory rate
- stale-memory rate

Lifecycle:
- temporal correctness
- conflict correctness
- deletion correctness
- resurrection count

Security:
- tenant leakage
- user leakage
- forbidden retrieval

Performance:
- extraction latency
- retrieval latency
- persistence latency
- token usage
- wall time

Failure attribution:
- LLM
- schema
- business validation
- DB
- vector
- pipeline/evaluator

Strongest cases:
- representative successes

Weakest cases:
- top failure classes

Portfolio evidence:
- only measured, defensible statements

Final status:
`COMPLETE` or `BLOCKED`

## Execution rules

- Current source wins.
- Preserve unrelated work.
- Never reset/stash/revert/clean.
- No commit/push unless explicitly requested.
- Do not modify production behavior merely to improve benchmark numbers.
- Freeze configuration before the held-out/full measurement.
- Report failures honestly.
- Do not start 1K/10K corpus scale work.
- STOP after MEMORY-EVAL-01.
