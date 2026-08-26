# RAG-04 — Real cross-encoder reranking

**Branch:** `feat/cross-encoder-reranking`

## Goal
Implement an optional learned reranker and make metrics truthful.

## Problem
Sort/dedupe by existing scores must not be presented as learned reranking.

## Primary scope
- `embedding/model inference boundary`
- `RAG backend client/graph/config`
- `metrics/UI/tests`

## Required behavior
- Explicit model/config and candidate depth.
- Stable scored ordering.
- Timeout/fallback policy recorded.
- Reranker metrics emitted only when it actually executed.

## Acceptance
- Disabled, success and failure paths tested; rank/score propagation correct.

## Measurement
MRR/nDCG/relevant-rank delta versus reranker latency/E2E p95.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
