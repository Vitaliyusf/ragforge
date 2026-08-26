# METRICS-01 — Metrics semantic corrections

**Branch:** `fix/metrics-semantics`

## Goal
Make retention/vector-growth/context-ratio metrics mean what their names imply.

## Problem
Operational windows/counters can be misleading if retention is shorter than UI window or operation count is labelled vector growth.

## Primary scope
- `docker-compose Prometheus config`
- `shared/vector metrics`
- `Gateway queries`
- `Retrieval/Pipeline UI/tests`

## Required behavior
- Retention covers supported windows or reports partial coverage.
- Separate vector operation count from points upserted/deleted.
- Use precise `cited_chunk_ratio` naming.

## Acceptance
- 500-point upsert increments point metric by 500; operation metric remains 1; 30d UI does not silently show 15d Prometheus data.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
