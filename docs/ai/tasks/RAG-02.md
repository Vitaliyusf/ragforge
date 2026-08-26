# RAG-02 — Bounded parallel subquery retrieval

**Branch:** `perf/rag-parallel-subquery-retrieval`

## Goal
Reduce Extended retrieval wall time without unbounded downstream fan-out.

## Problem
Independent rewrite/subquery searches are executed sequentially.

## Primary scope
- `conversation_graph.py`
- `RAG config/tests/instrumentation`

## Required behavior
- Use bounded TaskGroup/gather semantics.
- Preserve deterministic merge order and context/trace identity.
- Document partial/fail-fast error behavior.

## Acceptance
- Controlled-delay test proves overlap and configured max concurrency.
- Results remain deterministic.

## Measurement
Compare retrieval/E2E p50/p95 and downstream saturation before/after.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
