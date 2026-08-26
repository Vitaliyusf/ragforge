# FILES-01 — Fix Mongo transaction fallback semantics

**Branch:** `fix/files-transaction-fallback`

## Goal
Ensure repository transaction context yields exactly once and never pretends it can replay caller code.

## Problem
Transparent fallback after code inside a context manager has executed can violate generator/contextmanager semantics and correctness.

## Primary scope
- `backend/files/app/db/_base.py`
- `transaction callers/tests`

## Required behavior
- Determine topology support before entering caller block where possible.
- Yield exactly once.
- If a started transaction fails, propagate/handle at explicit operation retry boundary.

## Acceptance
- Standalone fallback, supported transaction and transaction failure paths are deterministic and tested.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
