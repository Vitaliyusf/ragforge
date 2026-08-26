# RAGForge AI Brain v2.2 — Optimized Validation Installation

This pack is already fully assembled. No manual editing inside AGENTS.md/CLAUDE.md/TESTING.md is required.

## If you already installed v2.1 Secure
Overwrite these files/directories from this pack:

```text
AGENTS.md
CLAUDE.md

backend/AGENTS.md
backend/CLAUDE.md
backend/rag/AGENTS.md
backend/rag/CLAUDE.md

frontend/AGENTS.md
frontend/CLAUDE.md

docs/ai/TESTING.md

scripts/ai/check.py
```

Everything else from v2.1 remains compatible.

## If installing from scratch
Copy the entire pack into the repository root, preserving paths.

## Gitignore
Keep:

```gitignore
/docs/ai/generated/*.json
/.agent-private/
```

## Initialize/validate
From the repository root:

```bash
python scripts/ai/init_private_brain.py
python scripts/ai/rebuild_repo_brain.py
python scripts/ai/validate_ai_memory.py
```

## Test the new validation helper

Focused:

```bash
python scripts/ai/check.py fast rag \
  --files backend/rag/app/services/eval_runner.py \
  --tests app/tests/test_eval_runner.py
```

Service:

```bash
python scripts/ai/check.py service rag
```

Successful commands should produce compact output.

## Agent final response
Codex and Claude are now instructed to always return:

```text
Commit title:
<copy-paste Conventional Commit title>

Commit description:
- <copy-paste bullet>
- <copy-paste bullet>
- <tests/compatibility note>
```

They still must not commit or push.
