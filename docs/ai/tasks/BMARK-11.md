# BMARK-11 — Prometheus benchmark snapshots

**Branch:** `feat/benchmark-prometheus-snapshots`

## Goal
Capture operational metrics automatically before/after the benchmark.

## Problem
Users should not manually export Prometheus dashboards for every experiment.

## Primary scope
- `existing Gateway metrics/Prometheus integration`
- `benchmark artifact storage/tests`

## Required behavior
- Before/after overview/latency/retrieval/quality/pipeline snapshots.
- Benchmark still succeeds if Prometheus unavailable.
- Use live/eval separation if available; no high-cardinality labels.

## Acceptance
- Available/unavailable/before-after tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
