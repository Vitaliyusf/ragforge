# BENCH-02 — System load, ingestion and RPC benchmarks

**Branch:** `feat/system-benchmarks`

## Goal
Measure full-system and ingestion/RPC bottlenecks reproducibly.

## Problem
Component benchmarks alone cannot expose queueing and pipeline tail latency.

## Primary scope
- `benchmarks/load`
- `benchmarks/ingestion`
- `benchmarks/rpc`

## Required behavior
- Chat concurrency Regular/Extended.
- Upload→searchable stage timings/throughput.
- RabbitMQ RPC latency/throughput.
- Explicit non-production target requirement.

## Acceptance
- Every result stores workload/config and can be compared without manual reconstruction.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
