# VECTOR-01 — Versioned incremental vector index lifecycle

**Branch:** `feat/vector-index-lifecycle`

## Goal
Support reproducible reindex, reuse and rollback without destroying the active collection.

## Problem
Embedding/chunk/index changes need explicit version metadata and safe cutover.

## Primary scope
- `files/embedding metadata`
- `vector schemas/Qdrant implementation/service/tests`

## Required behavior
- Content/config fingerprint metadata.
- Skip/reuse unchanged chunks.
- Build new physical collection and switch stable alias after validation.
- Rollback policy.

## Acceptance
- Stable fingerprint/reuse, changed-config invalidation, alias switch/rollback and tenant filtering tested.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
