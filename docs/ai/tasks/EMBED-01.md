# EMBED-01 — Canonicalize embedding runtime and retire legacy paths

**Branch:** `refactor/embedding-runtime`

## Goal
Make typed embedding job path canonical and remove duplicated legacy runtime after caller migration.

## Problem
Multiple legacy/typed consumers/handlers duplicate retry/chunk/transport behavior and operational threads.

## Primary scope
- `embedding main/consumers/services`
- `callers/topics/tests`
- `shared retry/import cleanup`

## Required behavior
- Prove caller/topic migration before deletion.
- One canonical embedding job path.
- Shared retry/DLQ imports without importlib path hacks when feasible.
- Lifecycle-owned reusable HTTP client.

## Acceptance
- All embedding callers/tests use canonical path; removed legacy code has no references.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
