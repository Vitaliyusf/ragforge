# EVAL-03 — Stale eval label validation

**Branch:** `feat/eval-stale-label-validation`

## Goal
Prevent deleted/rechunked golden labels from being counted as retrieval misses.

## Problem
Relevant file/chunk IDs may become stale after indexing/chunking changes.

## Primary scope
- `RAG eval runner/store`
- `tenant-scoped file/vector label validation path`
- `related tests`
- `minimal Eval UI state`

## Required behavior
- Validate relevant IDs before scoring where safely observable.
- Stale labels are reported separately from misses.
- Cross-tenant label existence cannot be leaked.

## Acceptance
- Deleted label is stale, existing label valid, cross-tenant lookup denied.
- Stale items are not silently scored as retrieval failures.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
