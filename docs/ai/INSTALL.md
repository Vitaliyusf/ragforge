# RAGForge Agent Context — Installation

The tracked repository contains the shared agent instructions. Generated operational state stays private and gitignored.

## Tracked files

- `AGENTS.md` — canonical Codex/shared entry point.
- `CLAUDE.md` — small Claude Code adapter importing `AGENTS.md`.
- `.claude/rules/*.md` — path-scoped Claude rules loaded only for matching files.
- `docs/ai/` — durable project/task/memory documentation.
- `scripts/ai/` — validation, handoff, and Repo Brain tooling.

Do **not** create nested `CLAUDE.md` copies merely to repeat root instructions. Use path-scoped `.claude/rules/` or an existing nested `AGENTS.md` only when a subtree genuinely needs additional constraints.

## One-time local setup

Ensure `.gitignore` contains:

```gitignore
/docs/ai/generated/*.json
/.agent-private/
CLAUDE.local.md
```

Initialize private operational memory if needed:

```bash
python scripts/ai/init_private_brain.py
```

Build the local Brain v4 database:

```bash
python scripts/ai/brain.py sync --full
```

Validate it:

```bash
python scripts/ai/brain.py doctor
python scripts/ai/validate_agent_context.py
python scripts/ai/validate_ai_memory.py
```

The existing generated JSON indexes remain supported during migration and can still be rebuilt when required by the memory protocol:

```bash
python scripts/ai/rebuild_repo_brain.py
```

## Claude Code

Claude Code reads `CLAUDE.md`, which imports `AGENTS.md`. Path-specific rules under `.claude/rules/` load when relevant files are opened.

After cloning or changing the instruction setup, start Claude Code and run `/context` to confirm `CLAUDE.md` is listed under memory files.

Local personal instructions belong in gitignored `CLAUDE.local.md`, not tracked project files.

## Codex

Codex uses root/nested `AGENTS.md`. The root file is intentionally a compact map; load detailed docs only when the task requires them.

## Public repository rule

Tracked AI memory must remain public-safe. Handoff/history, unresolved bugs, technical debt, failed approaches and operational details belong in `.agent-private/`.
