# SAFE-01 — Fail-closed streaming output safety

**Branch:** `fix/streaming-output-guardrail`

## Goal
Prevent blocked output tokens from reaching the browser before safety approval.

## Problem
Streaming before final output guardrail creates an irreversible exposure window.

## Primary scope
- `RAG generation/events/guardrail flow`
- `frontend stream assumptions if needed`
- `tests`

## Required behavior
- Approved output remains consistent with streamed output.
- Blocked output emits zero unsafe token events.
- Cancellation/timeouts bounded.
- TTFT semantics documented.

## Acceptance
- Regression test proves blocked output has zero token events.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
