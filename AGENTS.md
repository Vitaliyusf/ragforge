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

### 5.1 First validation action

At the first need to run Python tests/checks in a task:

```bash
python scripts/ai/check.py doctor
```

Run this once per task.

If it reports `BLOCKED`, do not spend many commands probing Python/uv/pytest/plugin combinations.
Report the environment problem unless environment repair is the task.

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
