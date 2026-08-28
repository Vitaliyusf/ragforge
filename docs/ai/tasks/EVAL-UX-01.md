# EVAL-UX-01 — Evaluation run report redesign

**Branch:** `refactor/eval-run-report`  
**Phase:** Frontend / Product Track  
**Depends on:** `FILES-LIST-01`

## Goal

Turn Eval from a long stack of cards/accordions into a coherent engineering run report that makes status, quality, failures, comparability, and next actions immediately understandable.

## Run report structure

```text
Run header
↓
Execution flow
↓
KPI summary
↓
Tabbed report
```

Suggested tabs:

```text
Overview
Retrieval
Quality
Failures
Items
Configuration
```

## Run header

Prefer human labels:
- profile name
- timestamp
- dataset
- item count
- duration
- status

Raw UUID remains secondary technical metadata.

## Execution flow

Show causal execution:

```text
Dataset validation → Retrieval → Regular E2E
```

A failed stage must clearly explain downstream skipped stages.

Do not imply skipped = failed.

## Failure UX

Primary error copy must be product-readable.

Structure:

```text
What happened
Impact
Likely cause (only when evidence supports it)
Next actions
Technical details
```

Raw exception text belongs under Technical details.

Actions may include:
- View trace
- Open relevant logs
- Retry run

Only show actions that actually work.

## Metrics

Prioritize:
- MRR
- Recall@K
- nDCG
- latency percentiles
- failure count
- groundedness / answer-quality metrics when available

Show sample size where relevant.

## Comparison integrity

If baseline/candidate configurations differ materially:

```text
Not directly comparable
```

must be visible before delta claims.

Show changed configuration fields.

Do not color a delta as "good" unless metric direction is defined.

## Items

The per-item view should support:
- filter by failure
- filter by score band
- search by ID/question
- inspect sources/results

Large item lists should remain responsive.

## Refactor touched scope

- remove duplicate metric-formatting logic
- remove duplicated card wrappers
- create stable run-report primitives
- keep run data transformation outside presentation
- remove dead Eval UI/styles in touched scope

## Tests

```text
eval focused tests
→ failed/skipped phase rendering
→ comparison comparability rules
→ metric/sample-size rendering
→ technical-details collapse
→ item filtering
→ full frontend suite once
→ production build
→ git diff --check
```

STOP. Do not start PRODUCT-01.
