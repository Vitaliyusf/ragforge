# DOCS-01 — Architecture credibility documentation

**Branch:** `docs/architecture-credibility`

## Goal
Make public claims match executable behavior and document key decisions.

## Problem
README drift damages credibility more than missing buzzwords.

## Primary scope
- `README.md`
- `docs/adr`
- `Mermaid sequence diagrams`
- `benchmark methodology links`

## Required behavior
- Implemented/Experimental/Planned capability table.
- Correct service/retrieval/reranker/streaming claims.
- ADRs for messaging, checkpoints, tenancy, eval, agents, outbox, citations, vLLM, vector lifecycle.

## Acceptance
- No fabricated benchmark numbers; public claims are traceable to current code.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
