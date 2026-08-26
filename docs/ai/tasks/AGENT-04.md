# AGENT-04 — Tenant-scoped general agent mode

**Branch:** `feat/rag-agent-mode`

## Goal
Add one real tool-calling application agent over existing tenant-scoped services.

## Problem
General agent capability should reuse secured service APIs rather than bypassing ownership or creating fake multi-agent choreography.

## Primary scope
- `new RAG agent module`
- `backend client/tool schemas`
- `mode wiring`
- `frontend selector if needed`
- `tests`

## Required behavior
- Tools such as KB search, memory search, list/get files, summarize/compare docs.
- Server-injected identity, tool allowlist, budgets/timeouts, sanitized bounded results.

## Acceptance
- Document comparison scenario uses real tools and citations; cross-tenant/tool abuse tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
