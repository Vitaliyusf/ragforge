# RAGForge Testing and Validation

The goal is to preserve correctness while minimizing repeated dependency setup, execution time and agent-context output.

## Core rule
Use progressive validation:

```text
during coding
→ focused checks

task complete
→ affected service suite

shared/release-wide change
→ full validation
```

CI remains the authoritative clean-environment validation.

## Development environment
Normal agent iterations must reuse:
1. repository `.venv` if present;
2. otherwise the currently active Python environment.

Do not normally run:

```bash
uv run --isolated --python 3.11 --with-requirements ...
```

for every Ruff/mypy/pytest invocation.

Fresh isolated dependency resolution belongs in CI or an explicit dependency/reproducibility task.

## Docker
Docker does not automatically save tokens or time.

Recommended split:

```text
Docker:
- MongoDB
- Kafka
- RabbitMQ
- Qdrant
- vLLM
- integration/system dependencies

Local .venv:
- Ruff
- mypy
- focused pytest
- service pytest when dependencies permit
```

Use Docker for integration tests that genuinely require the containerized stack.
Avoid rebuilding or creating a new test container for routine static/unit checks.

# Validation helper

Use:

```bash
python scripts/ai/check.py ...
```

It intentionally:
- captures normal command output;
- prints one compact PASS line on success;
- prints only the relevant tail on failure;
- avoids flooding Claude/Codex context.

## Tier 1 — FAST
Use repeatedly while implementing.

Example:

```bash
python scripts/ai/check.py fast rag \
  --files backend/rag/app/services/golden_set_parser.py \
          backend/rag/app/services/eval_runner.py \
  --tests app/tests/test_golden_set_parser.py
```

When mypy is justified:

```bash
python scripts/ai/check.py fast rag \
  --files backend/rag/app/services/golden_set_parser.py \
          backend/rag/app/services/eval_runner.py \
  --tests app/tests/test_golden_set_parser.py \
  --mypy
```

Tier 1 should normally include:
- changed-file Ruff;
- focused regression/unit tests;
- optional focused mypy.

Do not run the full service suite after every code edit.

## Mypy policy
Run mypy when:
- public/internal typed contracts changed;
- Pydantic/config/schema models changed;
- the changed module is already covered by mypy;
- task acceptance explicitly requires type checking.

Do not run mypy mechanically for every Python edit.

## Tier 2 — SERVICE
Run once near task completion.

RAG:

```bash
python scripts/ai/check.py service rag
```

Gateway:

```bash
python scripts/ai/check.py service gateway
```

Files:

```bash
python scripts/ai/check.py service files
```

Embedding:

```bash
python scripts/ai/check.py service embedding
```

Vector DB:

```bash
python scripts/ai/check.py service vector_db
```

Memory:

```bash
python scripts/ai/check.py service memory
```

LLM Agent:

```bash
python scripts/ai/check.py service llm_agent
```

Frontend:

```bash
python scripts/ai/check.py service frontend
```

For production-impacting frontend changes:

```bash
python scripts/ai/check.py service frontend --build
```

If a task changes multiple services/contracts, run the affected service suites.

## Tier 3 — FULL
Use only when:
- shared infrastructure/contracts changed;
- task acceptance explicitly requires repo-wide validation;
- doing final release/PR verification.

```bash
python scripts/ai/check.py full --fail-fast
```

Do not run this repeatedly during normal task implementation.

## Direct CI-equivalent commands
Use these only when debugging the helper or when a task explicitly needs the raw command.

### Ruff

```bash
ruff check backend/
```

### Backend service tests

From `backend/<service>`:

```bash
PYTHONPATH="$PWD:$PWD/.." pytest app/tests -q
```

Services:
- embedding
- files
- gateway
- llm_agent
- memory
- rag
- vector_db

### Shared tests

From `backend/`:

```bash
PYTHONPATH="$PWD" pytest shared/tests -q
```

Run shared tests from `backend/`, not `backend/shared/`.

### Frontend

```bash
cd frontend
npm test
```

Production-impacting frontend changes:

```bash
npm run build
```

## Output discipline
Passing:
```text
Ruff: PASS
Pytest focused: PASS
Overall: PASS
```

Failing:
```text
Pytest focused: FAIL
<only relevant tail/error>
```

Rules:
- no dependency install/resolution output unless the install itself is the task;
- no full passing pytest transcript;
- no full mypy transcript on success;
- during iteration prefer `--maxfail=1`;
- never hide or weaken a real failure.

## Brain/security validation
After meaningful AI-brain/memory changes:

```bash
python scripts/ai/rebuild_repo_brain.py
python scripts/ai/validate_ai_memory.py
```

Generated index JSON and `.agent-private/` remain gitignored.
