# EVAL-04 — Effective eval configuration snapshot

**Branch:** `fix/eval-effective-config-snapshot`

## Goal
Record what actually executed rather than legacy intent flags.

## Problem
Compatibility booleans such as hybrid/reranker flags may not correspond to active implementations.

## Primary scope
- `eval_store.py`
- `eval_runner.py`
- `RAG/embedding/vector config metadata`
- `tests`

## Required behavior
- Record effective retrieval strategy, candidate/context K, embedding/chunking metadata, pass2 config, actual reranker implementation/model.
- Unknown fields stay explicit null/unobserved.
- Older run documents remain readable.

## Acceptance
- Inactive hybrid/reranker cannot be reported as active merely because a legacy flag is true.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
