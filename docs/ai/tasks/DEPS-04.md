# DEPS-04 — Embedding library upgrade experiment

**Branch:** `chore/upgrade-embedding-stack`

## Goal
Evaluate sentence-transformers/model-stack upgrade without silently changing retrieval quality.

## Problem
Major embedding-library upgrades can alter model loading/performance/numerics.

## Primary scope
- `embedding requirements/implementation/tests/benchmark`

## Required behavior
- Same model/corpus/config before/after.
- Compatibility fixes isolated from retrieval algorithm changes.

## Acceptance
- Embedding tests pass.

## Measurement
Recall/MRR, embedding latency/batch throughput/memory before/after.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
