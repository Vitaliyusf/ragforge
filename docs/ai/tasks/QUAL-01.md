# QUAL-01 — Expected claim coverage

**Branch:** `feat/eval-expected-claim-coverage`

## Goal
Measure whether a grounded answer covers all required golden facts.

## Problem
Groundedness can be perfect while the answer omits required claims.

## Primary scope
- `eval_runner/store`
- `answer judge/matching if required`
- `Eval UI/tests`

## Required behavior
- Per-item expected/covered count and coverage.
- Missing expected claims => unmeasured, not zero.
- Judge metadata/version if semantic judge matching is used.

## Acceptance
- Case with fully grounded answer covering half the expected claims reports groundedness 100% and coverage 50%.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
