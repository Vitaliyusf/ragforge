# RAGForge AI Brain v2.4 — CI-Delegated Validation

If v2.3 is already installed, copy this package into the repository root and
overwrite the matching files.

Replace:

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

No manual editing is required.

After copying:

```bash
python scripts/ai/check.py doctor
python scripts/ai/rebuild_repo_brain.py
python scripts/ai/validate_ai_memory.py
```

Do NOT run all service suites merely because these instruction/helper files changed.

## New normal workflow

During coding:

```bash
python scripts/ai/check.py focused rag \
  --files <changed.py> \
  --tests <focused test files>
```

Cross-cutting/high-risk service change near completion:

```bash
python scripts/ai/check.py affected rag
```

NO-OP task:
- acceptance-focused tests only;
- no service suite;
- no full frontend suite;
- no repo-wide Ruff.

Full local validation is rare:

```bash
python scripts/ai/check.py full --fail-fast
```

GitHub CI remains the broad clean-environment validation.
