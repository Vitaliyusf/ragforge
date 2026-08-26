# BMARK-06 — Full diagnostic benchmark orchestrator

**Branch:** `feat/diagnostic-benchmark-runner`

## Goal
Run supported benchmark phases through one server-side workflow.

## Problem
The user should not execute separate manual eval commands for base/Regular/Extended/E2E.

## Primary scope
- `reuse EvalRunner/store`
- `benchmark run model/progress`
- `API/tests`

## Required behavior
- Separate evaluation_mode from pipeline_mode.
- Truthfully run only currently supported phases.
- Queued/running/completed/partial/failed/interrupted progress metadata.
- Item failures can be partial.

## Acceptance
- Phase order/progress/partial/full failure and mode tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
