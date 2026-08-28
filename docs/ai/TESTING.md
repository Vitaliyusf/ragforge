# RAGForge Testing Policy — CI-Delegated / Low-Token

## Principle

```text
Test what changed.
Do not make the coding agent re-run the whole CI pipeline.
```

The agent owns fast, relevant validation.
GitHub CI owns broad clean-environment validation.

## Level 0 — NO-OP audit

When current code already satisfies a task:

Run only acceptance-focused tests.

Example:

```text
BMARK-05 already implemented
→ hash/version tests
→ stale-label test
→ historical-run test
→ done
```

Do not run:
- full RAG suite;
- full gateway suite;
- full frontend suite;
- production build;
- repo-wide Ruff;
- full mypy;
- memory rebuild unless memory actually changed.

Expected final status:

```text
NO-OP VERIFIED
```

## Level 1 — Focused implementation tests

Use while coding.

```bash
python scripts/ai/check.py focused rag \
  --files backend/rag/app/services/eval_runner.py \
          backend/rag/app/services/eval_store.py \
  --tests app/tests/test_eval_runner.py \
          app/tests/test_eval_store.py
```

This runs:
- Ruff on changed Python files;
- only the named test files.

Add mypy only if justified:

```bash
... --mypy
```

Do not rerun a PASS unless later edits can invalidate it.

## Level 1b — Domain lane

Near completion, run the lane that owns the behavior you changed instead of a whole
service. Lanes are directories under each service's test tree, so the mapping stays
readable without a generated index.

```bash
python scripts/ai/check.py lane <lane>
```

| Lane | Covers |
| --- | --- |
| `shared` | `backend/shared/tests` — auth, transport, envelopes, redaction |
| `repo-contract` | repository guardrails (`tests/test_public_repo_guardrails.py`) |
| `gateway` | the whole gateway service |
| `gateway-auth` | authentication, RBAC, CSRF, security startup |
| `gateway-routes` | files, RAG, chat, memory and model-management routes |
| `gateway-observability` | metrics/eval routes, Prometheus client, correlation, logging |
| `gateway-compat` | error-body shapes kept for older clients |
| `rag-core` | regular/extended flow, retrieval, checkpoint/resume, context assembly, contracts |
| `rag-eval` | eval runner lifecycle, retrieval scoring, import, pipeline, validation, store |
| `rag-benchmark` | planning/profiles, execution/recovery, manifest, summary, export, comparison |
| `rag-metrics` | turn facts, citation metrics, graph instrumentation, metrics query |
| `rag-compat` | legacy/pre-versioning RAG behavior |
| `files-core` | ingestion flow, label resolution, service contract, tenant scope, metrics |
| `files-review` | review decisions, single-apply guards, what review state callers may read |
| `embedding` | canonical job pipeline, query embedding, model factory, config, health |
| `vector` | the whole vector_db service |
| `vector-qdrant` | the production Qdrant adapter contract |
| `vector-compat` | flat, pre-envelope request shapes |
| `llm-core` | budgets, structured output, streaming, observability, prompts, contracts |
| `llm-provider` | provider finish reasons, vLLM streaming usage, vLLM auth |
| `llm-compat` | legacy management/config handlers |
| `memory-core` | write policy, retrieval, chat API, handler contracts |
| `memory-agent` | chat exit, title generation, utility LLM calls, message parsing |
| `memory-compat` | legacy memory requests, deprecated insight surfaces |
| `frontend-chat` | chat feature tests |
| `frontend-files` | files feature tests |
| `frontend-eval` | eval feature tests |
| `frontend-metrics` | metrics/benchmark feature tests |
| `frontend-activity` | activity model and navigation activity |
| `frontend-websocket` | socket service |
| `frontend-shared-ui` | error boundary, HTTP client, store slices, render smoke tests |

Which lane to run:

- implementation iteration → the exact changed test files (Level 1);
- change inside one domain → that domain's lane;
- cross-cutting change inside a service → that service's affected suite, once;
- full repository → CI.

A `*-compat` lane holds behavior kept alive for older artifacts or APIs. Normal feature
work neither reads nor runs it. When a compatibility path is retired, delete the
production code and its compat tests together — never the test alone.

## Level 2 — Affected service

Use once near completion only for cross-cutting/high-risk service changes.

```bash
python scripts/ai/check.py affected rag
```

Examples that justify this:
- new RPC/action;
- repository/storage changes;
- tenant/security boundary;
- runner lifecycle/concurrency;
- broad service contract.

Examples that usually do not:
- small pure helper;
- local parser change;
- text/UI-only change;
- no-op audit.

## Level 3 — Full

Rare locally.

```bash
python scripts/ai/check.py full --fail-fast
```

Use only for:
- explicit CI-equivalent local validation;
- broad shared infrastructure/contracts;
- runtime/dependency/CI changes;
- release verification.

## Validation environment

`doctor` is a diagnostic tool, not a universal validation gate. Run it only when the
task or an observed environment failure calls for diagnosis:

```bash
python scripts/ai/check.py doctor
```

Do not repair `.venv` unless environment repair is the task. A missing or broken
`.venv` must not block task validation when an isolated run is available. An accepted
fallback is direct isolated Python 3.11, with the task's required tools or requirements:

```bash
uv run --isolated --python 3.11 ...
```

When isolated uv is needed, choose one workspace-local `UV_CACHE_DIR` at task start.
For each environment/tooling root cause, diagnose once and make at most one corrected
retry. If the canonical command still cannot run, report `BLOCKED`; do not rotate
through interpreters, virtualenvs, cache layouts, plugin sets or injected dependencies.

## CI parity and authoritative PASS

A local `PASS` is authoritative only when it uses the corresponding CI lane's
canonical dependency layers, Python/runtime version, `PYTHONPATH`/import roots,
pytest plugins, configuration files and required feature flags/environment.

Do not use `uv run ... --with <missing-package>` or another ad-hoc dependency to
convert a canonical-lane failure into `PASS`. Fix the canonical dependency owner or
report the canonical validation `BLOCKED`. A useful run made with extra non-CI
dependencies must be labeled exactly:

```text
NON-AUTHORITATIVE / ENVIRONMENT-ADJUSTED
```

Do not repeatedly probe:
- `.venv`;
- `py`;
- `python3`;
- `uv`;
- pytest plugin combinations.

If the environment cannot collect tests normally:

```text
BLOCKED
```

Do not disable plugin autoload and call the suite green.

## Test selection and ownership

Run the smallest suite that can falsify the change, and keep the complete suite in CI.
During iteration, use exact focused or domain tests. Run a full affected-service suite
once near completion only for cross-cutting or high-risk changes; reserve full-repository
validation mainly for CI, releases, or explicitly broad infrastructure work.

Each behavior should have a primary test layer:

- pure calculation: unit test;
- serializer/schema: contract test;
- graph/service wiring: integration or orchestration test;
- browser workflow: end-to-end test;
- supported historical artifact: compatibility lane.

Higher layers prove wiring rather than duplicate lower-layer truth tables.

## Compatibility lane

Keep compatibility tests first-class but isolated from normal behavior tests. When a
compatibility version is retired, delete its production path and tests together and
update the support policy.

Raw test count is not a quality or optimization target. Do not combine independent cases
into giant loops, delete valuable contract coverage, or otherwise game reported test count.

## Ruff

Normal task:

```text
changed files only
```

Do not run `ruff check backend/` locally just to validate an unrelated feature.
Repo-wide lint belongs to CI unless lint cleanup is the task.

## Mypy

Run only when:
- typed contracts changed;
- schema/config/Pydantic models changed;
- touched code is in the normal mypy scope;
- task acceptance requires it.

Do not repeatedly shrink the scope to get a green result.

If changed files intersect an authoritative static-analysis scope, run that exact
command once before completion. For changes under `backend/shared` or
`backend/gateway/app`, the authoritative scope is:

```bash
mypy backend/shared backend/gateway/app --config-file mypy.ini
```

File-by-file mypy is not an equivalent completion check.

## Frontend

During coding:

```bash
npm test -- <specific-test-file>
```

Near completion, run the feature lane rather than the whole suite:

```bash
python scripts/ai/check.py lane frontend-files
```

Do not run full frontend tests locally by default.

Run:

```bash
npm run build
```

only for production-impacting/cross-cutting frontend changes.

## Pytest integrity

Authoritative validation must not use:
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`;
- broad `-k "not ..."` exclusions;
- hidden collection errors;
- skipped failing async coverage.

Diagnostic runs may investigate an environment issue, but must be reported as diagnostic only.

## Output

PASS:

```text
Ruff: PASS
Pytest focused: PASS
Overall: PASS
```

BLOCKED:

```text
Pytest: BLOCKED
<first actionable environment error>
Overall: BLOCKED
```

FAIL:
- show only relevant failure tail;
- stop after first useful failure during implementation.

## Recommended task flow

```text
read task
→ audit current implementation
→ NO-OP? acceptance tests only → done

otherwise:
targeted implementation
→ focused tests
→ focused tests again only if later edits invalidate them
→ required domain/static checks
→ optional affected-service suite once
→ final diff audit
→ no more source/test edits
→ record handoff once
→ rebuild brain once
→ validate memory once
→ PR
→ GitHub CI broad validation
```
