# EVAL-07 — Deterministic failure attribution

**Branch:** `feat/eval-failure-attribution`

## Goal
Classify benchmark failures by observed RAG stage.

## Problem
Aggregate recall/quality scores do not say where a query failed.

## Primary scope
- `new focused eval failure-attribution module`
- `eval_runner.py`
- `tests`
- `Eval drilldown/aggregation`

## Required behavior
- Deterministic categories for stale/index/retrieval/ranking/pass2/context/generation/completeness/grounding.
- Insufficient evidence yields UNCLASSIFIED.
- Do not use an LLM to guess retrieval-stage failure.

## Acceptance
- Synthetic traces cover every deterministic category with stable unit tests.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
