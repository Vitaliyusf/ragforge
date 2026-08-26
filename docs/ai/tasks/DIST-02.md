# DIST-02 — Kafka delivery contracts and schema versioning

**Branch:** `feat/kafka-delivery-contracts`

## Goal
Make critical ingestion delivery semantics explicit and replay-safe.

## Problem
Auto-commit/buffered send behavior is insufficient for durable workflow claims without idempotency and tested replay.

## Primary scope
- `backend/shared/kafka_base.py`
- `critical files/embedding/vector consumers/producers`
- `event schemas/tests`

## Required behavior
- Classify critical vs noncritical topics.
- Manual commit for critical flows where appropriate.
- Versioned event_id/schema envelope.
- Idempotent critical consumers.

## Acceptance
- Kill after durable write before commit replays safely; duplicate event does not duplicate state; schema compatibility tested.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
