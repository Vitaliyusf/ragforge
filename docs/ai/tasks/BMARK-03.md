# BMARK-03 — Automatic filename label resolution

**Branch:** `feat/eval-file-label-resolution`

## Goal
Map expected filenames to real tenant-scoped uploaded file IDs automatically.

## Problem
Manual ID copying makes golden sets fragile and labor-intensive.

## Primary scope
- `Files scoped lookup`
- `RAG eval preparation`
- `Gateway/UI/tests`

## Required behavior
- Exact then harmless normalized match.
- Missing=UNRESOLVED_FILE; multiple=AMBIGUOUS_FILE_MATCH.
- Never silently choose ambiguous/cross-tenant file.

## Acceptance
- Ready/unresolved/ambiguous/unanswerable counts shown; cross-tenant tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
