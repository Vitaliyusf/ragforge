# QUAL-02 — Claim-citation edge evaluation

**Branch:** `feat/citation-edge-evaluation`

## Goal
Score whether each claim cites its own supporting evidence.

## Problem
Set-level cited-vs-supporting overlap can score swapped citations as perfect.

## Primary scope
- `citation_metrics.py`
- `answer evaluation schema/prompt`
- `metrics facts/query`
- `tests/UI`

## Required behavior
- Per claim cited_passage_ids + supporting_passage_ids.
- Edge precision; edge recall only with a defensible definition.
- Malformed judge output => unmeasured.

## Acceptance
- Swapped citations do not receive 100% edge precision.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
