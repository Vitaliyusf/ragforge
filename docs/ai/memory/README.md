# Shared Agent Brain / Memory

This directory is the canonical persistent project memory shared by Codex, Claude Code and future chats.

## Fast routing knowledge
Read/query these to avoid repository-wide searches:
- `SERVICES.json` — service ownership and interaction boundaries.
- `CAPABILITIES.json` — existing features and canonical implementations.
- `CONTRACTS.json` — cross-service/API/event ownership.
- `CALL_PATHS.md` — common end-to-end call paths.
- `SEARCH_HINTS.md` — symptom/request → likely first files.

## Durable engineering memory
Read only when relevant:
- `DECISIONS.json` — accepted/rejected architectural decisions and revisit conditions.
- `FAILED_APPROACHES.json` — approaches not to repeat unless revisit conditions change.
- `BUGS.json` — known defects/regressions.
- `TECH_DEBT.json` — intentionally deferred engineering work.
- `GOTCHAS.md` — short recurring traps.

## Cross-session/cross-agent continuity
- `CURRENT_STATE.md` — compact project state.
- `HANDOFF.md` — latest handoff; overwritten each meaningful task.
- `CHANGE_HISTORY.jsonl` — compact append-only task history.

## Generated source knowledge
`docs/ai/generated/` is rebuilt from source:

```bash
python scripts/ai/rebuild_repo_brain.py
```

Query both persistent and generated knowledge:

```bash
python scripts/ai/brain_query.py "pass2 retrieval ranking" --top 20
python scripts/ai/brain_query.py "file upload review" --top 20
python scripts/ai/brain_query.py "metrics prometheus pipeline" --top 20
```

Generated indexes are navigation aids, not truth. Current source/tests remain authoritative.

## Keep memory small
Do not store conversations. Record only information another agent/session would materially benefit from knowing.
