# BENCH-01 — Reproducible vLLM benchmark harness

**Branch:** `feat/vllm-benchmarks`

## Goal
Measure self-hosted inference throughput, TTFT and GPU pressure across controlled configs.

## Problem
Runtime tuning cannot be defended without repeatable workload/config/result metadata.

## Primary scope
- `benchmarks/vllm`
- `README/workloads/result schema`

## Required behavior
- Matrix for max_num_seqs/GPU util/prefix cache/concurrency/input-output length.
- p50/p95/p99 TTFT/E2E, tok/s, req/s, errors/OOM and GPU data when available.
- Record hardware/model/vLLM/Git/config.

## Acceptance
- Smoke/mock mode works without GPU; no large generated results committed by default.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
