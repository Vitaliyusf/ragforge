# RAG-01 — Fix Pass2 global ranking

**Branch:** `fix/rag-pass2-global-ranking`

## Goal
Allow high-quality second-pass candidates to compete for final context.

## Problem
Appending Pass2 after already-ranked Pass1 can leave superior Pass2 chunks outside production Top-K.

## Primary scope
- `backend/rag/app/services/conversation_graph.py`
- `RAG graph/instrumentation tests`

## Required behavior
- Combine Pass1+Pass2 before final global dedupe/ranking.
- Preserve highest appropriate score and provenance.
- Stable ties; Regular mode unchanged.

## Acceptance
- Regression test: six Pass1 chunks plus superior Pass2 chunk -> Pass2 chunk enters final context.
- Duplicate chunk appears once.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
