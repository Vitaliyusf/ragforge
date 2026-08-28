# Agent Task Workflow

## Normal task
1. User sends only a task ID, e.g. `Implement RAG-01.`
2. Agent reads root instructions.
3. Agent reads only `docs/ai/tasks/RAG-01.md`.
4. Agent inspects current implementation and direct tests.
5. Agent verifies the task is not already satisfied.
6. Agent checks Git state and creates/uses the task branch.
7. Agent implements only that task.
8. Agent runs focused tests, required authoritative static scopes, then broader affected checks.
9. Agent reports concise results and a recommended commit message.
10. Agent does not commit or push.
11. User reviews, then manually commits/merges.
12. Next task starts from updated `main`.

## If current main differs from task assumptions
Current code wins.
- If the task is already complete: make no changes; report evidence.
- If files moved: locate current symbols and continue narrowly.
- If a prerequisite is absent: stop and report the prerequisite instead of reimplementing a large hidden dependency.
- If a newer implementation makes the requested design obsolete: explain briefly and propose the smallest equivalent task.

## Dirty working tree
Never erase user changes.
If touched paths overlap with uncommitted work, stop and report.
If unrelated and the environment safely supports isolated work, continue without modifying those files.

## Token discipline
- Use task IDs.
- Read one task file, not the whole roadmap.
- Search symbols/direct callers, not repo-wide prose.
- Final response is a summary, not a tutorial.

## Unknown/new request
1. Query the shared brain using the user's own keywords.
2. Read matching capabilities/services/contracts/decisions/bugs/debt.
3. Inspect only the top source matches and direct callers/tests.
4. Map the request to an existing capability/task if possible.
5. Create a new task spec only when needed.
6. Never create a second implementation before checking capability/symbol/contract indexes.

When creating a task against a hotspot, include the behavior change, the local refactor
target for that same concern, any deletion candidates made obsolete, and a non-goal that
forbids a parallel implementation. Create a standalone refactor task only when cleanup is
genuinely cross-cutting or cannot safely accompany the behavior task.

## Cross-agent switching
Claude and Codex communicate through repository memory, not hidden chat state.
Before continuing another agent's work:
- read `.agent-private/HANDOFF.md` if present;
- inspect `git diff`;
- read referenced memory IDs;
- verify current tests/diff before extending work.
After work, update private handoff/history using `MEMORY_PROTOCOL.md`.

## Before editing
1. Read only the requested task plus relevant brain entries.
2. Search the existing capability/symbol/call path before creating a new implementation.
3. Identify whether any touched file is already a hotspot.
4. State internally which concern owns the change.

## While editing
- Implement the task.
- Apply the task's local refactor budget to the same concern.
- If the new behavior supersedes a path and zero supported callers remain, remove the old path in the same task.
- Do not create compatibility wrappers by default.
- Do not create new generic helper modules.

## Before final response
Report:
- behavior result;
- focused/service validation;
- production files added/deleted;
- hotspot line count before/after where relevant;
- legacy/duplicate paths removed;
- any deliberately deferred cleanup and why.

## Environment
`doctor` is opt-in per task, not a universal prerequisite.
Do not repair `.venv` unless explicitly required.
A missing or broken `.venv` must not by itself block task validation.
When local Python is unsuitable, direct `uv run --isolated --python 3.11` is an accepted fallback.
Use one workspace-local `UV_CACHE_DIR` for isolated uv. Diagnose an environment root
cause once and make at most one corrected retry; then report `BLOCKED` rather than
changing interpreters, virtualenvs, cache layouts or injecting dependencies.

Local `PASS` requires parity with the matching CI lane's canonical dependencies,
runtime, import roots, plugins, configuration and required environment. An adjusted
run with extra non-CI dependencies is `NON-AUTHORITATIVE / ENVIRONMENT-ADJUSTED`.

After implementation and all validation, perform the final diff audit and make no
more source/test edits. Only then record handoff once, rebuild the brain once and
validate memory once. If code changes afterward, repeat validation and replace the
premature handoff at the end.
