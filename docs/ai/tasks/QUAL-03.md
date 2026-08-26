# QUAL-03 — Deterministic claim support metrics

**Branch:** `feat/claim-quality-metrics`

## Goal
Derive claim counts/rates and severity from auditable primitives.

## Problem
An aggregate LLM hallucination label hides denominator and can vary independently of claim support.

## Primary scope
- `answer evaluation schema`
- `metrics_facts/query`
- `eval/UI/tests`

## Required behavior
- claim_count, supported_count, unsupported_count, unsupported_rate.
- Versioned explicit severity policy.
- Judge parse failure => unmeasured.

## Acceptance
- 1 unsupported/2 and 1 unsupported/20 produce distinct rates; no claims does not masquerade as zero hallucination.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
