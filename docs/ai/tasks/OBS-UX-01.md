# OBS-UX-01 — Observability product workflows

**Branch:** `feat/observability-product-workflows`  
**Phase:** Frontend / Product Track  
**Depends on:** `PRODUCT-01` and sufficient backend trace/metrics contracts

## Goal

Connect Chat, Knowledge, Eval, Metrics, Logs, and Health into one inspectable operational workflow.

Do not create fake observability in the frontend.

## Cross-screen deep links

Implement only when real identifiers/contracts exist:

```text
Chat answer
→ trace

Eval failure
→ trace

Knowledge ingestion failure
→ ingestion trace

Metrics anomaly
→ affected traces

Health degradation
→ filtered logs
```

Preserve tenant/security scope.

## Metrics trust contract

Metrics UI should consume or derive explicit metadata equivalent to:

```text
value
unit
sample_count
scope
time_range
source
freshness
status
```

A metric must never silently appear tenant-scoped when it is global.

## Scope presentation

Clearly distinguish:
- tenant
- platform/global
- model
- pipeline
- selected time range

If a page-level filter does not apply to a component, show that explicitly.

## Empty / stale / partial

Do not use `—` as the only semantic state.

Support where meaningful:
- no data
- loading
- stale
- delayed
- partial
- unavailable

Example:
```text
No conversational traffic in this period
```

or:
```text
Global · data delayed 4m
```

## Metrics structure

Preserve useful domain tabs:
```text
Overview
Latency
Retrieval
Quality
Pipeline
```

Improve:
- sample counts
- p50/p95/p99
- comparison to previous period when supported
- hover details
- drill-down to underlying traces/issues

## Pipeline metrics

Represent real flow/loss, not equal decorative bars.

Example:
```text
Uploaded → Extracted → Chunked → Embedded → Indexed
```

Show stage losses and allow drill-down to affected documents when supported.

## Logs

Make trace/request/correlation identifiers actionable where possible.

Prefer structured event presentation with raw JSON as secondary detail.

## Health

Differentiate:
- liveness
- readiness
- dependency health
- SLO/operational health when available

Do not infer SLO health from readiness alone.

## Refactor touched scope

- centralize metric formatting/scope display
- centralize trace/deep-link builders
- remove duplicate log/health status formatting
- avoid parallel frontend-only observability state

## Tests

```text
metric scope/sample tests
→ empty/stale/partial state tests
→ deep-link tests
→ pipeline-loss rendering
→ health/log cross-link tests
→ full frontend suite once
→ production build
→ git diff --check
```

STOP. Do not start FRONT-POLISH-01.
