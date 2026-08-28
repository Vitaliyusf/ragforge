# BMARK-08 — Benchmark retrieval diagnostics

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Branch:** `feat/benchmark-retrieval-diagnostics`

## Goal
Attach structured candidate/rank/provenance traces to benchmark items.

## Problem
Aggregate scores alone cannot explain why an item failed.

## Primary scope
- `existing RAG trace/retrieval instrumentation`
- `benchmark result binding`
- `tests`

## Required behavior
- Base candidates/ranks/scores; Pass1/Pass2 trigger/query/candidates; merged/final context IDs/provenance where applicable.
- No unbounded private text.
- Normal user payload remains small.

## Acceptance
- One item trace explains candidate movement end-to-end.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
