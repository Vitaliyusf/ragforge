# Testing Commands

The GitHub Actions workflow is the canonical reference. Commands below mirror the current repository structure.

## Fast checks
From repository root:

```bash
ruff check backend/
mypy backend/shared backend/gateway/app --config-file mypy.ini
```

## Backend service tests
Each service imports itself as `app.*` and shared as `shared.*`.

Example RAG:

```bash
cd backend/rag
PYTHONPATH="$PWD:$PWD/.." pytest app/tests -q
```

Other services use the same form:

```bash
cd backend/<service>
PYTHONPATH="$PWD:$PWD/.." pytest app/tests -q
```

Current CI service matrix:
- embedding
- files
- gateway
- llm_agent
- memory
- rag
- vector_db

## Shared tests

```bash
cd backend
PYTHONPATH="$PWD" pytest shared/tests -q
```

Run from `backend/`, not `backend/shared/`, to avoid `shared/logging.py` shadowing stdlib `logging`.

## Repo guardrails

```bash
pytest tests/test_public_repo_guardrails.py -q
```

## Frontend

```bash
cd frontend
npm test
```

For production-impacting frontend changes also:

```bash
npm run build
```

## Validation selection
- Pure RAG metric helper: focused RAG tests + Ruff.
- RAG graph/runtime behavior: full RAG suite; add Gateway tests if transport/API changed.
- Files repository/ingestion: Files suite; Shared tests if shared primitives changed.
- Shared messaging/auth/errors: Shared suite + every directly affected service suite.
- Frontend component only: focused Vitest; build when routing/runtime/dependency/bundle behavior changes.
- Dependency/runtime/Docker upgrade: affected tests + frontend build as applicable + compose/config validation.

## Rules
- Never remove/relax assertions merely to make CI green.
- If a dependency/service needed for an integration test is unavailable, report the test as not executed with reason; do not claim a pass.

## AI brain consistency
After meaningful source/memory changes:

```bash
python scripts/ai/rebuild_repo_brain.py
python scripts/ai/validate_ai_memory.py
```
