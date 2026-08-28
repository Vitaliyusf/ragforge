# Optimized Agent Validation

Goal: preserve correctness while minimizing repeated environment setup, execution time and agent-token output.

## Environment rule
`doctor` is opt-in diagnostic help, not a universal task gate.

Prefer an existing suitable project/dev environment:
1. repository `.venv` if present;
2. otherwise the currently active Python environment.

Do not repair `.venv` unless environment repair is the task. A missing or broken `.venv`
must not block validation: direct `uv run --isolated --python 3.12` is an accepted fallback.
Avoid fresh dependency installation on every iteration; clean-environment authority remains CI.

An authoritative local `PASS` must preserve the matching CI lane's dependency
layers, runtime, import roots, plugins, configuration and required environment.
Extra non-CI dependencies may support diagnosis, but the result must be reported as
`NON-AUTHORITATIVE / ENVIRONMENT-ADJUSTED`, not `PASS`. Fix a missing package in its
canonical dependency owner or report the canonical run `BLOCKED`.

For isolated uv, use one workspace-local `UV_CACHE_DIR`. Diagnose the same
environment root cause once, make at most one corrected retry, then report `BLOCKED`
instead of cycling through interpreters, virtualenvs, caches or dependency injections.

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

### Tier 1b — DOMAIN LANE
Run the lane that owns the changed behavior, not the whole service.

```bash
python scripts/ai/check.py lane files-review
python scripts/ai/check.py lane frontend-metrics
```

The full lane table lives in `TESTING.md`. Compatibility lanes (`*-compat`) stay out of
normal feature work.

### Tier 2 — SERVICE
Run once near task completion only for cross-cutting or high-risk service changes.

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

## Test-suite ratchet

- Select exact focused/domain tests during iteration; do not optimize for a smaller raw test count.
- Each behavior has one primary test layer; higher layers prove wiring without duplicating every lower-layer case.
- Keep security, tenant isolation, recovery, idempotency and provenance coverage unless the production contract is retired.
- Keep supported historical behavior in an isolated compatibility lane.
- When compatibility code is retired, delete its tests and update the support policy in the same task.
- Do not combine independent cases into one giant loop solely to reduce reported test count.
- Split test monoliths by stable behavior ownership when that improves focused selection.
- Keep shared fakes in one `_*_harness.py` per service rather than re-declaring them per file.
- Avoid autouse fixtures at directory scope: an identity or environment fixture that only
  some modules need belongs in those modules, not in a lane `conftest.py`.

## Mypy policy
Do not run mypy automatically for every Python edit.

Run it when:
- a typed public/internal contract changed;
- Pydantic/config/schema models changed;
- the touched module is already covered by mypy;
- task acceptance explicitly requires it.

Otherwise focused pytest + Ruff is usually sufficient during iteration.

When changed files intersect an authoritative static-analysis scope, that exact
scope is mandatory once before completion. Changes under `backend/shared` or
`backend/gateway/app` require:

```bash
mypy backend/shared backend/gateway/app --config-file mypy.ini
```

File-by-file mypy is not equivalent.

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
