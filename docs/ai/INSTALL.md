# Secure One-Time Installation

## 1. Copy the pack into the RAGForge repository root
Preserve paths:
- `AGENTS.md`
- `CLAUDE.md`
- `.claude/`
- `backend/AGENTS.md`, `backend/CLAUDE.md`
- `backend/rag/AGENTS.md`, `backend/rag/CLAUDE.md`
- `frontend/AGENTS.md`, `frontend/CLAUDE.md`
- `docs/ai/`
- `scripts/ai/`

Review diffs before overwriting an existing setup.

## 2. Update `.gitignore`
Add:

```gitignore
/docs/ai/generated/*.json
/.agent-private/
```

Keep `docs/ai/generated/README.md` tracked.

## 3. Initialize private operational memory

```bash
python scripts/ai/init_private_brain.py
```

It refuses to create `.agent-private/` unless Git ignores it.

## 4. Generate local repository indexes

```bash
python scripts/ai/rebuild_repo_brain.py
```

Generated JSON is local-only; do NOT commit it.

## 5. Validate security/memory

```bash
python scripts/ai/validate_ai_memory.py
```

## 6. Review Git state

```bash
git status --short
git diff --check
```

`.agent-private/` and `docs/ai/generated/*.json` must NOT appear as tracked/staged files.

## Claude
Default `.claude/settings.json` is conservative:
- file/shell actions prompt normally;
- only narrow read-only Git commands are auto-allowed;
- destructive Git commands are denied.

Optional `.claude/settings.fast.example.json` auto-accepts edits while preserving the same command restrictions. Review it manually before copying over `settings.json`.

## Codex
Codex uses root/nested `AGENTS.md`.

## Public repository rule
Tracked AI memory must remain public-safe. Unresolved bugs, security findings, technical debt, handoff and detailed work history belong in `.agent-private/`.

For cross-machine/cloud continuity, use a separate private repo/storage source for `.agent-private/`.

## Suggested one-time commit

```text
chore(ai): add secure shared agent brain and task registry
```
