# PERF-01 — Async RAG persistence and checkpoint retention

**Branch:** `perf/rag-async-persistence`

## Goal
Remove sync persistence blocking from async RAG hot paths and bound checkpoint growth.

## Problem
Sync PyMongo/time.sleep and repeated full checkpoint snapshots can block event-loop work and amplify storage.

## Primary scope
- `conversation_persistence.py`
- `metrics_facts.py`
- `eval_store.py where hot`
- `conversation_graph.py/config/tests`

## Required behavior
- Async PyMongo or explicit bounded offload.
- No blocking sleep on async path.
- Checkpoint TTL/pruning policy preserving recovery/failed diagnostics.

## Acceptance
- Recovery semantics remain correct; TTL/pruning tested; no direct blocking sleep in touched async path.

## Measurement
Event-loop lag, TTFT/E2E p95, persistence latency and storage/write volume before/after.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
