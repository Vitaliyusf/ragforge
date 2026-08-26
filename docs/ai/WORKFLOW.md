# Agent Task Workflow

## Normal task
1. User sends only a task ID, e.g. `Implement RAG-01.`
2. Agent reads root instructions.
3. Agent reads only `docs/ai/tasks/RAG-01.md`.
4. Agent inspects current implementation and direct tests.
5. Agent verifies the task is not already satisfied.
6. Agent checks Git state and creates/uses the task branch.
7. Agent implements only that task.
8. Agent runs focused tests, then broader affected checks.
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

## Cross-agent switching
Claude and Codex communicate through repository memory, not hidden chat state.
Before continuing another agent's work:
- read `docs/ai/memory/HANDOFF.md`;
- inspect `git diff`;
- read referenced memory IDs;
- verify current tests/diff before extending work.
After work, update handoff/history using `MEMORY_PROTOCOL.md`.
