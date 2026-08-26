# BMARK-04 — Deterministic chunk labels and readiness

**Branch:** `feat/eval-chunk-label-resolution`

## Goal
Resolve expected facts to chunks when deterministic matching is safe and verify corpus readiness.

## Problem
File-level labels are useful but chunk-level diagnosis needs current chunk IDs without LLM-generated ground truth.

## Primary scope
- `tenant-scoped chunk repository/lookup`
- `eval preparation/readiness`
- `UI/tests`

## Required behavior
- Normalized exact substring/whitespace matching only.
- Multiple legitimate chunks allowed.
- Unresolved fact stays explicit; file-level eval remains usable.
- Check file exists/not deleted/searchable where observable.

## Acceptance
- Chunk resolution/readiness and tenant-isolation tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
