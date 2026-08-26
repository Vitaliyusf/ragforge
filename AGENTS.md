# RAGForge — Shared Agent Instructions

This is the canonical project instruction file for coding agents. Keep it short. Persistent project knowledge lives under `docs/ai/`; load only what the current task needs.

## Task lookup and navigation
- If the user names a task ID, read only `docs/ai/tasks/<TASK-ID>.md`.
- For a new/unclear request, first query the shared brain:
  `python scripts/ai/brain_query.py "<user request keywords>" --top 20`
- Then inspect only the strongest matching implementation files, direct callers and tests.
- If the generated index is stale/missing, run:
  `python scripts/ai/rebuild_repo_brain.py`
- Before creating a helper/service/component, search `CAPABILITIES.json`, `SERVICES.json`, `CONTRACTS.json`, generated symbols, and direct references.
- Do not scan the entire repository by default.

## Git safety
Before edits:
- `git status --short`
- `git branch --show-current`
- `git rev-parse HEAD`

Rules:
- Never reset, clean, stash, discard, overwrite, rebase, amend, merge, cherry-pick, commit or push user work.
- One task = one branch = one coherent change.
- Use the branch named in the task file. If the host manages the worktree/branch, preserve it and report it.
- If uncommitted work overlaps files you need to edit, stop and report.

## Source of truth
1. Current executable code/tests.
2. Current task file.
3. `docs/ai/memory/CURRENT_STATE.md` and registries.
4. Durable decisions/failed approaches/bugs/debt.
5. Architecture docs.
6. README/public docs.

Current code wins over stale documentation.

## Avoid duplicate implementations
Before adding functionality:
- Search `docs/ai/memory/CAPABILITIES.json`.
- Search `SERVICES.json` / `CONTRACTS.json` / `CALL_PATHS.md`.
- Search generated symbols/routes/config indexes.
- Search direct callers/imports.
Prefer extending/calling the owning service over reimplementing its logic elsewhere.

## Shared cross-agent memory
The repository memory under `docs/ai/memory/` is canonical across Codex, Claude and new chats.
- Continuing previous work → read `HANDOFF.md`.
- Architecture/technology change → read `DECISIONS.json`.
- Before retrying an old idea → read `FAILED_APPROACHES.json`.
- Touching an area with known issues → read `BUGS.json` and `TECH_DEBT.json`.
- End of a meaningful write task → follow `MEMORY_PROTOCOL.md`.
- Record only durable facts with evidence; do not store chat transcripts.

## Engineering invariants
- Preserve tenant isolation and backend authorization.
- Tenant/user identity comes from trusted server context, never client/model input.
- Reuse existing infrastructure before adding dependencies/services/frameworks.
- Avoid blocking I/O in async request paths.
- Use classes for lifecycle/state/policy/repository/resource ownership; keep pure calculations/transforms as functions.
- Unknown/unmeasured metrics = `null`, not fake `0`.
- Never fabricate benchmark improvements.
- Never add high-cardinality Prometheus labels such as tenant/run/file/dataset/trace IDs.
- Never expose secrets, cookies, auth tickets, unrestricted env vars or unbounded private document text.
- Preserve backward compatibility unless explicitly changed.

## Validation
Read `docs/ai/TESTING.md`.
- Focused tests first; broader affected suites second.
- Never weaken tests merely to obtain a pass.
- Python: relevant pytest + Ruff; mypy where covered.
- Frontend behavior: focused Vitest; production-impacting changes also `npm run build`.
- Performance claims require `docs/ai/BENCHMARKING.md`.

## Final response
Keep it concise:
1. Branch/effective worktree.
2. Changed files.
3. 3–7 implementation bullets.
4. Tests/checks + results.
5. Shared-memory records updated (IDs only).
6. Risks/unverified items.
7. Recommended Conventional Commit message.

Never commit or push.

## On-demand knowledge
- `docs/ai/PROJECT_CONTEXT.md`
- `docs/ai/REPO_MAP.md`
- `docs/ai/ENGINEERING_RULES.md`
- `docs/ai/SECURITY.md`
- `docs/ai/TESTING.md`
- `docs/ai/BENCHMARKING.md`
- `docs/ai/DECISIONS.md`
- `docs/ai/TASK_INDEX.md`
- `docs/ai/memory/README.md`
