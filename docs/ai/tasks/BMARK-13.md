# BMARK-13 — Benchmark Center UI

**Branch:** `feat/benchmark-center-ui`

## Goal
Provide prepare→run→progress→summary→download workflow with minimal user intervention.

## Problem
The backend workflow needs one focused UI instead of manual calls or a larger monolithic EvalPanel.

## Primary scope
- `new metrics/components/benchmark`
- `benchmark hooks/service`
- `HTTP abort plumbing`
- `tests`

## Required behavior
- Import/prepare/readiness, full-run action, optional E2E confirmation, phase progress, summary, ZIP download.
- Visibility-aware terminal polling and real AbortSignal propagation.

## Acceptance
- Happy/blocked/partial/failed/progress/download tests plus `npm run build`.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
