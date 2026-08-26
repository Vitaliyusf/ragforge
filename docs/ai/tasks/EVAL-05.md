# EVAL-05 — Eval run leases and crash recovery

**Branch:** `feat/eval-run-leases`

## Goal
Recover eval runs left `running` after process/container death.

## Problem
In-process asyncio exception handling cannot execute when the process is killed.

## Primary scope
- `eval_runner.py`
- `eval_store.py`
- `RAG startup/reconciliation`
- `tests`
- `minimal status UI`

## Required behavior
- Worker/heartbeat/lease metadata.
- Atomic stale-run reconciliation.
- Explicit interrupted/failure semantics.

## Acceptance
- Fresh lease remains running; expired lease is recovered exactly once; completed run untouched.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
