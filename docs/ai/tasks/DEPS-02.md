# DEPS-02 — Qdrant client upgrade

**Branch:** `chore/upgrade-qdrant-client`

## Goal
Bring qdrant-client closer to the deployed server generation and validate API changes.

## Problem
Old client versions can block newer supported operations and make server/client behavior harder to reason about.

## Primary scope
- `vector_db requirements/Qdrant implementation/tests`

## Required behavior
- Upgrade only after checking current server compatibility.
- Adapt deprecated APIs deliberately.
- No retrieval/filter semantic changes.

## Acceptance
- Vector suite passes including search/upsert/delete/count/tenant filters.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
