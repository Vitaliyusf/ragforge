# DIST-02 — Version Kafka delivery contracts and strengthen idempotency

**Order:** 49  
**Phase:** 7 Distributed production  
**Priority:** P2  
**Branch:** `feat/kafka-delivery-contracts`  
**Depends on:** `DIST-01`, `TEST-01`

## Goal
Make durable ingestion event schemas, retry policy and idempotency explicit across producer/consumer releases.

## Primary scope
- `Files/Embedding/Vector Kafka envelopes`
- `shared Kafka contract helpers`
- `consumer retry/DLQ/tests`

## Required behavior
- Add schema_version/message_id/correlation/causation/producer/timestamp as appropriate.
- Version payloads.
- Define retryable vs non-retryable failures.
- Define offset commit semantics.
- Ensure duplicate/replay side effects are idempotent.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Delete copied envelope builders once canonical contract is adopted.

## Non-goals
- No exactly-once claim.

## Validation
- Producer-consumer contract tests
- Kafka integration duplicate/replay tests

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
