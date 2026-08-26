# Shared Memory Update Protocol

Use this after every meaningful **write** task.

## Before work
1. If continuing prior work, read `HANDOFF.md`.
2. Search relevant `DECISIONS.json`, `FAILED_APPROACHES.json`, `BUGS.json`, `TECH_DEBT.json`.
3. Query the brain before creating new functionality.
4. Refresh generated index if missing/stale.

## After work
Always:
1. Run relevant tests/checks.
2. `python scripts/ai/rebuild_repo_brain.py`
3. Replace `HANDOFF.md` with a concise latest handoff.
4. Append exactly one compact line to `CHANGE_HISTORY.jsonl`.
5. `python scripts/ai/validate_ai_memory.py`

Conditionally:
- Durable architecture/technology choice → add/update `DECISIONS.json`.
- Failed/rejected approach worth avoiding → add `FAILED_APPROACHES.json`.
- Newly discovered unresolved defect → add/update `BUGS.json`.
- Intentional deferred work → add/update `TECH_DEBT.json`.
- New/relocated canonical capability → update `CAPABILITIES.json`.
- Changed service ownership/contract → update `SERVICES.json` / `CONTRACTS.json`.
- New recurring trap → add one short `GOTCHAS.md` item.

## Evidence
Every durable record requires evidence: source path/symbol, test, task, benchmark run, PR/commit once known, or reproducible observation.
Never state speculation as fact. Use `status: "suspected"` if not verified.

## Stable IDs
- `DEC-###`
- `FAIL-###`
- `BUG-###`
- `DEBT-###`
- `CAP-###`
- `CON-###`

Never reuse an ID.

## HANDOFF.md
Overwrite; do not append forever. Keep under ~120 lines.
Include:
- task / agent / branch / HEAD / status
- what changed
- touched files
- tests/checks
- memory IDs added/updated
- unresolved items
- exact next recommended step
- safe for manual commit: yes/no

Do not copy chat text.

## CHANGE_HISTORY.jsonl
One compact JSON object per meaningful task:

```json
{"ts":"ISO-8601","agent":"codex|claude|human","task":"RAG-01|null","branch":"...","summary":"...","files":["..."],"tests":["..."],"memory_ids":["BUG-001"],"result":"completed|partial|blocked"}
```

## Decisions
An accepted decision remains authoritative until superseded or a listed `revisit_if` condition becomes true. Do not reopen it because another technology is fashionable.

## Failed approaches
Do not retry an active failed/rejected approach unless:
- a `revisit_if` condition is now true, or
- the user explicitly requests reevaluation.

## Technical debt
Do not silently fix unrelated debt in another task. Record it with impact/evidence/future-task suggestion unless correctness/security requires immediate action.

## Bugs
Mark `fixed` only when fix + regression test (where practical) + relevant tests exist.
