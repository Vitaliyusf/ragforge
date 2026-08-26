# BMARK-09 — Benchmark failure attribution

**Branch:** `feat/benchmark-failure-attribution`

## Goal
Aggregate deterministic stage-failure categories over diagnostic runs.

## Problem
A user should see retrieval/ranking/pass2/context/generation failure counts without manual trace inspection.

## Primary scope
- `reuse EVAL-07 attribution module if present`
- `benchmark aggregation/UI/tests`

## Required behavior
- Per-item category+evidence and aggregate counts/rates.
- UNCLASSIFIED for insufficient evidence.

## Acceptance
- Every deterministic category has test coverage; no LLM retrieval-stage guessing.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
