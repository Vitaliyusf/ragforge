# AGENT-02 — Structured memory tool protocol and termination

**Branch:** `refactor/memory-agent-tool-protocol`

## Goal
Replace prose-only tool results and ambiguous done semantics with typed outcomes.

## Problem
The model should not infer success/failure from free text; `done` should deterministically stop further mutations.

## Primary scope
- `memory agent/tool executor/schemas`
- `ChatExit integration`
- `tests`

## Required behavior
- Typed result with ok/code/retryable/id.
- Accepted done/finalize prevents subsequent mutation.
- Structured run completion status.

## Acceptance
- Failed mutation cannot be misread as success; no mutation executes after done.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
