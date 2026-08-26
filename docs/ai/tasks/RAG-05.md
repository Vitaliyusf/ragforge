# RAG-05 — True dense+sparse hybrid retrieval

**Branch:** `feat/hybrid-retrieval`

## Goal
Add real lexical/sparse retrieval and deterministic fusion while preserving filters.

## Problem
Dense Qdrant search alone is not hybrid search.

## Primary scope
- `embedding sparse representation if needed`
- `Qdrant schema/search`
- `RAG retrieval strategy/config/tests`

## Required behavior
- Explicit dense/sparse/hybrid strategies.
- Independent candidates + RRF/default deterministic fusion.
- Tenant/review/retrieval filters in every path.
- Dense-only migration compatibility.

## Acceptance
- Dense, sparse, hybrid, duplicate-fusion and tenant-filter tests pass.

## Measurement
Dense vs sparse vs hybrid vs hybrid+reranker Recall/MRR/nDCG and p95.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
