# BMARK-10 — Benchmark quality and latency summary

**Branch:** `feat/benchmark-result-summary`

## Goal
Produce one machine-readable summary of existing retrieval/quality/performance metrics.

## Problem
The downloadable bundle needs consistent denominators/percentiles rather than UI-only values.

## Primary scope
- `benchmark summary module`
- `existing metric helpers`
- `tests`

## Required behavior
- IR, answer-quality and failure metrics when available.
- sample_count/mean/min/max/p50/p95/p99 semantics.
- null for unmeasured; valid JSON only.

## Acceptance
- Empty/partial/missing-stage/low-sample tests pass without NaN/Infinity.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
