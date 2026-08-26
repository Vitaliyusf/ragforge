# Install v2.3 changed files

If v2.2 is already installed, copy this ZIP into the repository root and overwrite the matching files.

Files replaced:

```text
AGENTS.md
CLAUDE.md
backend/rag/AGENTS.md
backend/rag/CLAUDE.md
docs/ai/TESTING.md
docs/ai/memory/MEMORY_PROTOCOL.md
scripts/ai/check.py
```

`BMARK04_THREAD_AUDIT_V2_3.md` is informational; you do not need to copy it into the repository.

After copying:

```bash
python scripts/ai/check.py doctor
python scripts/ai/rebuild_repo_brain.py
python scripts/ai/validate_ai_memory.py
```

Do not run full service suites merely because these instruction/helper files changed.

For future tasks, Codex/Claude should:
- use the task file + targeted brain query;
- avoid broad repo scans;
- run doctor once;
- never bypass pytest plugins to claim green;
- run focused checks during coding;
- run each affected service suite once near completion;
- finalize memory only after code is frozen;
- return copy-paste commit title + description.
