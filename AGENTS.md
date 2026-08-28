# RAGForge — Agent Entry Point

Canonical shared instructions for Codex and other coding agents. Claude Code imports this file through `CLAUDE.md`.

**Goal:** correct changes with the smallest useful context, minimal repository exploration, and no duplicated validation work.

## Source of truth

Use this order when sources disagree:

1. Current executable code and tests.
2. The active task spec in `docs/ai/tasks/`.
3. Canonical runtime/security/architecture docs in `docs/ai/`.
4. Durable memory records in `docs/ai/memory/`.
5. Historical task/handoff text last.

Never let an old task, handoff, benchmark note, or README override current code or `docs/ai/RUNTIME_CONTRACT.md`.

## Start a task

1. Inspect Git state once: `git status --short`, `git branch --show-current`, `git rev-parse HEAD`.
2. If a task ID is named, read only `docs/ai/tasks/<TASK-ID>.md` first.
3. Locate current ownership with the local repo brain before broad search:
   `python scripts/ai/brain.py query "<task-id> <goal>" --top 12`.
4. Inspect the returned implementation/tests and direct callers only.
5. If acceptance criteria are already satisfied, return **NO-OP VERIFIED** and run only acceptance-focused checks.

Do not begin with repo-wide `rg`, reading hundreds of files, generated indexes, or whole historical memory.

If the brain reports stale state and retrieval is needed, run:

```bash
python scripts/ai/brain.py sync
```

## Execution efficiency

- Use the Repo Brain first; avoid broad repository exploration when targeted retrieval is sufficient.
- Use at most 2 Brain query refinements before targeted file inspection.
- Do not repeat inventory, searches, benchmarks, or evidence already available for the active task.
- Never print/read an entire source file over ~250 lines unless the whole file is genuinely required; inspect symbols or bounded line ranges first.
- After Brain retrieval, inspect no more than ~8 initial implementation/test files before deciding whether more context is actually needed.
- Do not perform a feature-wide file inventory unless the active task explicitly requires an inventory.
- During implementation, run only the smallest focused tests that cover the change.
- Run affected/domain validation once near completion and the full relevant suite at most once.
- Do not rerun a passing validation unless relevant source changed afterward.
- Do not probe multiple runtimes, repair `.venv`, or alter dependencies to make validation pass.
- Use the repository's canonical runtime. After one diagnosed environment retry, report `BLOCKED`.
- Do not create extra benchmarks, comparisons, profiler runs, or old-vs-new experiments unless required by acceptance criteria or needed to prove a non-obvious regression.
- Keep investigation and progress reporting concise; do not narrate every command.
- Once acceptance criteria are satisfied and required validation is green, **STOP**. Do not look for additional improvements.

## Navigation map

Load details only when the task requires them:

- Architecture/project context: `docs/ai/PROJECT_CONTEXT.md`, `docs/ai/REPO_MAP.md`
- Runtime/dependency authority: `docs/ai/RUNTIME_CONTRACT.md`
- Engineering rules: `docs/ai/ENGINEERING_RULES.md`
- Security/tenancy: `docs/ai/SECURITY.md`
- Testing and lanes: `docs/ai/TESTING_OPTIMIZED.md`, `scripts/ai/check.py`
- Workflow: `docs/ai/WORKFLOW.md`
- Benchmarking: `docs/ai/BENCHMARKING.md`
- Durable decisions/contracts: `docs/ai/memory/`
- Memory write protocol: `docs/ai/memory/MEMORY_PROTOCOL.md`
- Repo-brain design/commands: `docs/ai/BRAIN_V4.md`

## Engineering invariants

- Preserve tenant isolation and authorization; identity comes only from trusted server context.
- Reuse existing services/contracts before creating parallel implementations.
- Avoid blocking I/O on async request paths.
- Preserve backward compatibility unless the task explicitly changes a contract.
- Unknown/unmeasured metrics are `null`, never invented `0` values.
- Never fabricate benchmark/performance improvements.
- Avoid high-cardinality Prometheus labels.
- Never expose secrets or unbounded private document content.
- Keep changes scoped to the active task; do not repair unrelated issues unless they block it.

Path-specific Claude rules under `.claude/rules/` add backend/frontend/RAG/test guidance only when relevant files are opened.

## Git safety

Never reset, clean, stash, discard, rebase, amend, merge, cherry-pick, commit, or push user work unless the user explicitly requests that exact Git action.

If uncommitted work overlaps files the task must modify, stop and report the overlap. Do not erase it.

## Validation

Local validation is focused feedback; CI owns broad clean-environment validation.

At the first need for Python validation in a task:

```bash
python scripts/ai/check.py doctor
```

During implementation, run changed-file Ruff plus the smallest directly relevant tests. Prefer named lanes:

```bash
python scripts/ai/check.py lane <lane>
```

Run an affected-service suite once only for a cross-cutting/high-risk service change. Run full repository validation only when the task explicitly requires it or shared CI/runtime infrastructure changed broadly.

Never manufacture green results by disabling pytest plugin autoload, excluding real failures, injecting ad-hoc dependencies into a canonical lane, or shrinking an authoritative mypy scope.

## Finalization

After source/test state is stable:

```text
focused validation
→ optional affected-service validation
→ git diff --check / diff --stat / status
→ durable memory update only if canonical behavior changed
→ private handoff once
→ python scripts/ai/brain.py sync
→ legacy brain rebuild once if required by the existing memory protocol
→ memory/context validation once
→ final response
```

Do not repeatedly rebuild memory while implementation is still moving.

## Final response

Return:

1. Branch/effective worktree.
2. Changed files.
3. What changed (concise bullets).
4. Validation with truthful `PASS` / `FAIL` / `BLOCKED` / `SKIP`.
5. Memory IDs updated, if any.
6. Risks/unverified items.
7. Copy-paste Conventional Commit title.
8. Copy-paste commit description.

Do not commit or push unless explicitly requested.
