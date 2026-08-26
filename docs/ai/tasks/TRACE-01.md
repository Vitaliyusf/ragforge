# TRACE-01 — Structured retrieval diagnostics

**Branch:** `feat/rag-retrieval-diagnostics`

## Goal
Make candidate movement through retrieval observable for admin/eval diagnosis.

## Problem
Current execution trace identifies stages/latency but not enough candidate/rank/provenance information.

## Primary scope
- `conversation_graph.py`
- `conversation_tracing.py`
- `trace event types/tests`
- `admin/debug surfaces if needed`

## Required behavior
- Pass1 queries/candidates/rank/score.
- Pass2 trigger reasons/query/candidates.
- Final candidate/context IDs and provenance.
- Bounded, sanitized, admin/eval-only details.

## Acceptance
- One trace can explain what each retrieval pass found and which chunks reached generation.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
