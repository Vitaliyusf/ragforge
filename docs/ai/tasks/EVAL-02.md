# EVAL-02 — Dataset version and canonical hash

**Branch:** `feat/eval-dataset-versioning`

## Goal
Make eval datasets and historical runs reproducible.

## Problem
A dataset can change while retaining the same identity, making old/new runs appear comparable when labels differ.

## Primary scope
- `backend/rag/app/services/eval_store.py`
- `backend/rag/app/services/eval_runner.py`
- `related eval tests`
- `minimal Eval UI metadata if already exposed`

## Required behavior
- Add deterministic dataset version/hash over scoring-relevant canonical content.
- Every run snapshots dataset ID/version/hash.
- Old datasets/runs remain readable.

## Acceptance
- Equivalent canonical content hashes identically.
- Scoring-relevant change creates a new version/hash.
- Historical run metadata does not mutate.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
