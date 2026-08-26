# One-Time Installation

The ZIP is structured as an overlay for the repository root.

## Recommended
1. Make sure you are in the `ragforge` repository root.
2. Copy the contents of this pack into the repository **preserving paths**.
3. Review the diff.
4. Commit these instruction files **once** to `main` so every future Codex/Claude branch inherits them.

Suggested setup commit:

```text
chore(ai): add persistent agent instructions and task registry
```

This one-time setup commit is different from normal implementation tasks: the task agents themselves are instructed never to commit.

## Windows PowerShell
If the extracted pack is at `C:\temp\ragforge_ai_agent_setup` and the repo is at `C:\src\ragforge`:

```powershell
$src = "C:\temp\ragforge_ai_agent_setup"
$dst = "C:\src\ragforge"
Copy-Item -Path "$src\*" -Destination $dst -Recurse -Force
Copy-Item -Path "$src\.claude" -Destination $dst -Recurse -Force
Set-Location $dst
git status --short
git diff -- AGENTS.md CLAUDE.md .claude docs/ai backend/AGENTS.md backend/CLAUDE.md backend/rag/AGENTS.md backend/rag/CLAUDE.md frontend/AGENTS.md frontend/CLAUDE.md
```

## WSL / Linux / macOS

```bash
cp -a /path/to/ragforge_ai_agent_setup/. /path/to/ragforge/
cd /path/to/ragforge
git status --short
git diff -- AGENTS.md CLAUDE.md .claude docs/ai backend/AGENTS.md backend/CLAUDE.md backend/rag/AGENTS.md backend/rag/CLAUDE.md frontend/AGENTS.md frontend/CLAUDE.md
```

## Claude Code
Claude Code automatically reads project `CLAUDE.md`. Nested `CLAUDE.md` files are scoped to their subtrees.

`.claude/settings.json` in this pack:
- auto-accepts file edits for lower interaction overhead;
- pre-allows common read-only Git/test commands;
- denies commit/push/reset/clean/stash/rebase/merge/cherry-pick.

Review this file before using it. Remove `defaultMode: acceptEdits` if you prefer confirmation for edits.

## Codex
Codex reads `AGENTS.md`; nested `AGENTS.md` files apply to their directory subtrees. No extra repo config is required.

## Daily workflow
After setup, normal prompts should be tiny:

```text
Implement RAG-01.
```

The task file supplies:
- branch name;
- problem;
- scope;
- acceptance criteria;
- relevant tests.

After you manually merge a finished branch, start the next task from updated `main`.

## Initialize the shared repository brain
After copying this pack into RAGForge:

```bash
python scripts/ai/rebuild_repo_brain.py
python scripts/ai/validate_ai_memory.py
```

You may commit generated indexes with the one-time AI setup so remote agents have an immediate index; they can always regenerate it.

Recommended one-time setup commit:

```text
chore(ai): add shared agent brain and task registry
```

After setup:

```text
Implement RAG-01.
```

Unknown issue:

```text
Diagnose: <one sentence>. Use the repository brain first.
```

Switching Claude ↔ Codex:

```text
Continue from HANDOFF.md.
```
