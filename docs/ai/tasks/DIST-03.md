# DIST-03 — Distributed tenant-aware rate limiting

**Branch:** `fix/distributed-rate-limits`

## Goal
Fix local bucket accounting and make limits meaningful across replicas/AI workloads.

## Problem
Per-IP rejection can consume global capacity and process-local limits multiply with replicas.

## Primary scope
- `shared rate limiter`
- `Gateway middleware/config/tests`
- `distributed backend only if justified`

## Required behavior
- Correct global/per-IP accounting.
- Tenant identity from auth context.
- Requests/concurrency/tokens quotas where observable.
- Explicit outage policy.

## Acceptance
- Abusive IP cannot drain global tokens through rejected requests; multi-replica semantics are tested/documented.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
