# Shared Agent Brain / Memory — Security Model

This directory contains only **public-safe, durable project knowledge** suitable for a public repository.

## Tracked/public-safe memory
- `SERVICES.json` — service ownership.
- `CAPABILITIES.json` — canonical implementations.
- `CONTRACTS.json` — cross-service contracts.
- `CALL_PATHS.md` / `SEARCH_HINTS.md` — navigation.
- `DECISIONS.json` — sanitized durable decisions.
- `GOTCHAS.md` — sanitized engineering traps.
- `CURRENT_STATE.md` — sanitized current architecture state.

Never put secrets, customer data, private prompts/documents, unpublished vulnerability details, private branch names, local absolute paths, or incident details here.

## Private operational memory
Operational cross-agent memory lives in:

```text
.agent-private/
```

and MUST be gitignored.

It contains:
- `HANDOFF.md`
- `CHANGE_HISTORY.jsonl`
- `BUGS.json`
- `TECH_DEBT.json`
- `FAILED_APPROACHES.json`

Create it with:

```bash
python scripts/ai/init_private_brain.py
```

The init script refuses to proceed unless `.agent-private/` is ignored by Git.

## Generated indexes
`docs/ai/generated/*.json` are also local-only and gitignored. They are reproducible navigation indexes, not source files to commit.

Generate:

```bash
python scripts/ai/rebuild_repo_brain.py
```

Query public + private + generated knowledge:

```bash
python scripts/ai/brain_query.py "pass2 retrieval ranking" --top 20
```

## Public repository rule
If the repository is public, never store unresolved security findings or private operational history in tracked files. For cross-machine/cloud continuity, sync `.agent-private/` through a separate private repository/storage location, not a public branch.
