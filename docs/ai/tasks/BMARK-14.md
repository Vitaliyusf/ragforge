# BMARK-14 — Benchmark run comparison

**Branch:** `feat/benchmark-run-comparison`

## Goal
Compare a candidate run against a compatible previous baseline.

## Problem
Manual spreadsheet comparison wastes time and can hide incompatible configs.

## Primary scope
- `run comparison backend/helper`
- `BenchmarkComparison UI`
- `export comparison.json`
- `tests`

## Required behavior
- Baseline/candidate/absolute delta/meaningful percentage delta.
- Warn on dataset/config/model/retrieval incompatibility.
- Missing/zero-denominator safe handling.

## Acceptance
- Compatible and mismatch cases tested.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
