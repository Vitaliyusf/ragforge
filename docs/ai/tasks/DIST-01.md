# DIST-01 — Canonical turn persistence with outbox

**Branch:** `feat/conversation-outbox`

## Goal
Remove browser-coordinated dual writes and make completed turns server-authoritative.

## Problem
RAG and browser/Memory persistence can diverge if the client disconnects after RAG completion.

## Primary scope
- `RAG turn persistence`
- `outbox/event publisher`
- `Memory projection consumer`
- `ChatContext persistence removal`
- `tests`

## Required behavior
- Atomically persist Turn + TurnCommitted outbox record.
- At-least-once publish + turn_id idempotency.
- Browser only renders/refreshes projection.

## Acceptance
- Crash before publish, duplicate delivery, Memory outage and browser disconnect preserve one canonical turn without duplicate projection.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
