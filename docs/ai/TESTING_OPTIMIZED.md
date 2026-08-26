# Optimized Agent Validation

Goal: preserve correctness while minimizing repeated environment setup, execution time and agent-token output.

## Environment rule
Do not use `uv run --isolated --with-requirements ...` for normal iterative validation.

Use the existing project/dev environment:
1. repository `.venv` if present;
2. otherwise the currently active Python environment.

Clean/fresh dependency installation belongs in CI, not every agent iteration.

## Progressive validation

### Tier 1 — FAST
Use while implementing.

Run only:
- Ruff on changed files.
- Focused regression/unit tests.
- Mypy only when the changed typed contract/module benefits from it.

Example:

```bash
python scripts/ai/check.py fast rag \
  --files backend/rag/app/services/golden_set_parser.py \
          backend/rag/app/services/eval_runner.py \
  --tests app/tests/test_golden_set_parser.py \
  --mypy
```

Do not repeatedly run the full service suite while iterating.

### Tier 2 — SERVICE
Run once near task completion.

```bash
python scripts/ai/check.py service rag
```

For frontend production-impacting work:

```bash
python scripts/ai/check.py service frontend --build
```

### Tier 3 — FULL
Run only when:
- shared infrastructure/contracts changed;
- the task explicitly requires repo-wide validation;
- preparing a release/manual PR verification.

```bash
python scripts/ai/check.py full --fail-fast
```

CI remains the authoritative clean-environment validation.

## Mypy policy
Do not run mypy automatically for every Python edit.

Run it when:
- a typed public/internal contract changed;
- Pydantic/config/schema models changed;
- the touched module is already covered by mypy;
- task acceptance explicitly requires it.

Otherwise focused pytest + Ruff is usually sufficient during iteration.

## Docker
Docker does not inherently save tokens.

Recommended split:
- Docker: MongoDB, Kafka, RabbitMQ, Qdrant, vLLM and integration dependencies.
- Local `.venv`: Ruff, mypy and focused unit/service pytest.
- Docker: integration/system tests that genuinely require containerized dependencies.

Avoid rebuilding/creating a fresh test container for every static/unit check.

## Output discipline
Successful checks must be quiet:
- one PASS line per check;
- no dependency-resolution/install logs;
- no full pytest output when passing.

On failure:
- print only the relevant tail/error section;
- stop after the first useful failure during iteration.

The helper `scripts/ai/check.py` implements this behavior.
