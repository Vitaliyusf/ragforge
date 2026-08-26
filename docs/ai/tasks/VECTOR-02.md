# VECTOR-02 — Qdrant operation optimizations

**Branch:** `perf/qdrant-operations`

## Goal
Avoid unnecessary exact counts and ID scrolling for routine metrics/deletes.

## Problem
Exact count and scroll-all-IDs-before-filter-delete can add network/CPU/memory overhead at scale.

## Primary scope
- `qdrant.py`
- `vector service/metrics/tests`

## Required behavior
- Use approximate collection point count for routine metrics where acceptable.
- Use filter-based delete when supported by current client/server.
- Preserve tenant/document filter semantics.

## Acceptance
- Delete does not need to materialize all IDs; exact reconciliation remains available only where explicitly needed.

## Measurement
Compare delete/count latency and memory on representative point counts.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
