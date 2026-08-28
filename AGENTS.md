# RAGForge — Shared Agent Instructions

This is the canonical project instruction file for Codex and other coding agents.
Claude Code imports it through the root `CLAUDE.md`.

Primary objective: correctness with minimal unnecessary repository exploration,
test duplication, environment churn and agent-context output.

## 1. Task startup

If the user names a task ID:

1. Read only `docs/ai/tasks/<TASK-ID>.md`.
2. Inspect current code before editing.
3. If the task appears already implemented, audit the acceptance criteria first.
4. If every acceptance criterion is already satisfied, treat the task as **NO-OP VERIFIED**:
   - do not create a branch unless required;
   - do not edit code;
   - run only the acceptance-focused tests needed to verify it;
   - do not run service-wide/full-repository suites;
   - return why no changes were needed.

If task paths are insufficient, run one targeted repository-brain query:

```bash
python scripts/ai/brain_query.py "<TASK-ID> <goal keywords>" --top 12
```

Do not start with broad repo-wide scans.

## 2. Exploration budget

Start with:
- at most 2 targeted search/query commands;
- approximately 6 directly relevant implementation/test files.

Expand only when a direct caller/import/contract proves another area is required.

Prefer:
- exact symbol searches;
- narrow line ranges;
- direct imports/callers;
- existing focused tests.

Avoid by default:
- `rg --files backend frontend`
- broad `rg` over whole backend/frontend
- reading large files in full
- rereading files already inspected in the same task
- reading generated JSON indexes directly

Use `brain_query.py` instead of manually scanning generated indexes.

## 3. Git safety

At task start run once:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
```

Rules:
- Never reset, clean, stash, discard, rebase, amend, merge, cherry-pick, commit or push user work.
- One task = one coherent change.
- If branch creation is blocked by the host, do not repeatedly retry.
- If overlapping uncommitted work exists, stop and report it.
- Do not fix unrelated existing issues unless they block the task and the user asks.

## 3a. Runtime and tooling authority

`docs/ai/RUNTIME_CONTRACT.md` is the canonical source for Python/Node versions,
dependency layers, the isolated-uv fallback, the authoritative mypy scope and the
pinned Ruff version. It, `.python-version` and CI config override generic runtime
text embedded in older task specs, handoffs, historical docs or benchmark records,
unless the active task explicitly owns a runtime/toolchain migration.

All workspace-local task/tool caches belong under `.agent-private/tooling/<task-id>/`
when possible. Never create task-local cache directories at the repository root such
as `.uv-cache-<task>` or `.uv-python-<task>`.

## 4. Engineering invariants

- Preserve tenant isolation and authorization.
- Tenant/user identity comes only from trusted server context.
- Reuse existing services/contracts before creating new ones.
- Avoid blocking I/O in async request paths.
- Unknown/unmeasured metrics = `null`, never fake `0`.
- Never fabricate benchmark or performance improvements.
- Do not introduce high-cardinality Prometheus labels.
- Do not expose secrets or unbounded private document text.
- Preserve backward compatibility unless the task explicitly changes a contract.

## 5. Validation philosophy

**Test what changed. Let CI test the repository.**

Local agent validation is not a duplicate CI pipeline.

The repository CI already owns clean-environment, repo-wide validation.
Agents should optimize for fast, relevant feedback while preserving correctness.

A local `PASS` is authoritative only when the command preserves the corresponding
CI lane's canonical environment assumptions: dependency/requirements layers,
Python version, import roots, pytest plugins, configuration and required feature
flags/environment. Never add an ad-hoc dependency such as `uv run --with
<missing-package>` to turn a canonical-lane failure into `PASS`. Fix the canonical
dependency owner or report `BLOCKED`; if an adjusted run is still useful, label it
`NON-AUTHORITATIVE / ENVIRONMENT-ADJUSTED`.

### 5.1 First validation action

At the first need to run Python tests/checks in a task:

```bash
python scripts/ai/check.py doctor
```

Run this once per task.

If it reports `BLOCKED`, do not spend many commands probing Python/uv/pytest/plugin combinations.
Report the environment problem unless environment repair is the task.

When isolated uv is required, establish one workspace-local `UV_CACHE_DIR` for the
task under `.agent-private/tooling/<task-id>/`. Diagnose an environment/tooling root cause once and make at most one corrected
retry for that root cause. If canonical validation still cannot run, report `BLOCKED`;
do not cycle through interpreters, virtualenvs, cache layouts or dependency injections.

### 5.2 During implementation — focused only

Run the smallest tests that directly exercise changed behavior:

```bash
python scripts/ai/check.py focused <service> \
  --files <changed files> \
  --tests <focused tests>
```

Use:
- Ruff on changed Python files;
- focused unit/regression tests;
- focused frontend component tests when UI changed.

Do not run service-wide suites after every edit.
Do not rerun a passing focused check unless later edits can invalidate it.

### 5.3 Mypy

Do not run mypy mechanically on every Python edit.

Run it only when:
- the task changes typed public/internal contracts;
- Pydantic/config/schema models changed;
- the changed code is inside the repository's normal mypy scope;
- task acceptance explicitly requires it.

If run, use the intended scope once and rerun the same scope after fixes.
Do not shrink the scope repeatedly just to obtain a green command.

If changed files intersect an authoritative static-analysis scope, run that exact
scope once before completion. In this repository, changes under `backend/shared` or
`backend/gateway/app` require:

```bash
mypy backend/shared backend/gateway/app --config-file mypy.ini
```

File-by-file mypy is not equivalent to that authoritative scope.

### 5.3a Test lanes

Backend tests are grouped by behavior ownership into directories under each
service's test tree, and frontend tests by feature directory. Select a lane
instead of a whole service:

```bash
python scripts/ai/check.py lane <lane>
```

```text
shared                  backend/shared/tests: auth, transport, envelopes, redaction
repo-contract           repository guardrails + repo-brain/tooling contract tests

gateway                 the whole gateway service
gateway-auth            authentication, RBAC, CSRF, security startup
gateway-routes          files, RAG, chat, memory, model-management routes
gateway-observability   metrics/eval routes, Prometheus client, correlation, logging
gateway-compat          error-body shapes kept for older clients

rag-core                regular+extended flow, retrieval, checkpoint/resume, context, contracts
rag-eval                eval runner lifecycle, retrieval scoring, import, pipeline, store
rag-benchmark           planning/profiles, execution/recovery, manifest, summary, export
rag-metrics             turn facts, citation metrics, graph instrumentation, metrics query
rag-compat              legacy/pre-versioning RAG behavior

files-core              ingestion flow, label resolution, service contract, tenant scope
files-review            review decisions, single-apply guards, review-state exposure

embedding               canonical job pipeline, query embedding, model factory, config, health

vector                  the whole vector_db service
vector-qdrant           the production Qdrant adapter contract
vector-compat           flat, pre-envelope request shapes

llm-core                budgets, structured output, streaming, observability, contracts
llm-provider            provider finish reasons, vLLM streaming usage, vLLM auth
llm-compat              legacy management/config handlers

memory-core             write policy, retrieval, chat API, handler contracts
memory-agent            chat exit, title generation, utility LLM calls, message parsing
memory-compat           legacy memory requests, deprecated insight surfaces

frontend-chat           chat feature
frontend-files          files feature
frontend-eval           eval feature
frontend-metrics        metrics/benchmark feature
frontend-activity       activity model and navigation activity
frontend-websocket      socket service
frontend-shared-ui      error boundary, HTTP client, store slices, render smoke tests
```

Which lane to run:

- implementation iteration → the exact changed test files;
- change inside one domain → that domain's lane;
- orchestration change → the service's `*-core` lane plus the relevant domain lane;
- compatibility change → that service's `*-compat` lane;
- cross-cutting/high-risk change → the affected service suite once;
- full repository → CI.

A `*-compat` lane holds behavior kept alive for older artifacts/APIs. Normal
feature tasks neither read nor run it. Compatibility cases that cannot be
separated from their own module's builders stay in place and carry the
registered `compat` marker instead, so the whole compatibility surface is
selectable either way:

```bash
python scripts/ai/check.py lane rag-compat   # the compat/ directory
pytest app/tests -m compat                   # every compat case, wherever it lives
pytest app/tests -m "not compat"             # feature work
```

When a compatibility path is retired, delete the production code and its
compat tests together — never the test alone.

Shared fakes live in one `_*_harness.py` per service (for example
`backend/files/app/tests/_files_harness.py`). Fixtures that every lane may need
are re-exported from a `conftest.py`; an autouse fixture only some modules need
is imported by those modules, never by a lane-wide `conftest.py`.

Full collection/duration inventory goes to a private file, not the transcript:

```bash
python scripts/ai/check.py inventory rag
```

### 5.4 Before finishing — affected service suite only when justified

Run a service-wide suite once only when the change is cross-cutting/high-risk inside that service.

Examples that justify it:
- new RPC/action/route;
- persistence/repository behavior;
- service-wide contract change;
- async lifecycle/concurrency;
- security/tenant boundary;
- significant eval-runner behavior.

Examples that usually do **not** justify it:
- pure helper;
- parser-only local change;
- small rendering-only UI change;
- docs/memory-only change;
- NO-OP audit.

Command:

```bash
python scripts/ai/check.py affected <service>
```

If multiple services changed materially, run each affected service once.

### 5.5 Frontend

During implementation:
- run only the relevant Vitest file(s).

Before finishing:
- do **not** run the entire frontend suite locally by default;
- run `npm run build` only when production-impacting UI/API integration, routing,
  build configuration or shared frontend behavior changed.

GitHub CI owns the full frontend test suite.

### 5.6 Full repository validation

Do not run full repository validation locally by default.

Use:

```bash
python scripts/ai/check.py full --fail-fast
```

only when:
- the task explicitly requests CI-equivalent local validation;
- shared infrastructure/contracts changed broadly;
- CI/runtime/dependency tooling itself changed;
- preparing a release where local full validation is specifically useful.

### 5.7 Ruff

During normal task work:
- Ruff changed files only.

Do not run repo-wide Ruff merely to validate an unrelated task.
Repo-wide lint is CI responsibility unless lint/CI cleanup is the task.

### 5.8 Pytest integrity

Never manufacture a green result by:
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` as authoritative validation;
- broad `-k "not ..."` exclusions;
- hiding collection errors;
- skipping failing async tests;
- suppressing real failures.

Environment/plugin incompatibility means `BLOCKED`, not `PASS`.

### 5.9 Validation output

Success should be compact:

```text
Ruff: PASS
Pytest focused: PASS
Overall: PASS
```

On failure:
- print only the relevant error tail;
- stop at the first useful failure during implementation.

Do not dump dependency install/resolution logs or full passing-test transcripts into agent context.

## 6. CI delegation

For normal feature work:

```text
agent focused tests
→ optional affected-service suite once
→ PR
→ GitHub CI performs broad validation
```

Do not duplicate all CI jobs locally.

If no code changed:
- run only acceptance-focused tests;
- no service-wide/full suites;
- no build unless acceptance explicitly requires it.

## 7. Finalization and memory

Do memory work only after code/test state is stable:

```text
implementation
→ focused validation
→ optional affected-service validation
→ final diff audit
→ memory updates
→ brain rebuild once
→ memory validation once
→ final response
```

Do not rebuild/validate the brain multiple times while code is still changing.
Do not run `record_handoff.py`, `rebuild_repo_brain.py` or
`validate_ai_memory.py` until implementation, validation and the final diff audit
are complete and no more source/test edits are expected. Record the handoff once,
then rebuild once and validate once. Any later code edit makes that handoff premature.

Prefer `scripts/ai/record_handoff.py` over manually reading/rewriting full handoff/history.

## 8. Final diff audit

Before memory/final response:

```bash
git diff --check
git diff --stat
git status --short
```

Inspect only changed hunks that still need review.
Do not dump huge diffs into context.

## 9. Final response

Always return:

1. Branch/effective worktree.
2. Changed files.
3. What changed — 3–7 concise bullets.
4. Validation with truthful `PASS` / `FAIL` / `BLOCKED` / `SKIP`.
5. Memory records updated — IDs only.
6. Risks/unverified items.
7. Copy-paste Git commit title.
8. Copy-paste Git commit description.

If no code changed, explicitly say:

```text
NO-OP VERIFIED
```

and explain which acceptance tests proved it.

Use:

```text
Commit title:
<Conventional Commit title>

Commit description:
- <behavior/change>
- <important compatibility/security point>
- <validation performed>
- <remaining limitation if relevant>
```

Do not commit or push.
