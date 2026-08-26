# RAGForge AI Development Pack

This directory is the durable project knowledge base for Codex and Claude Code.

The root `AGENTS.md` and `CLAUDE.md` are intentionally small. They act as maps, not encyclopedias. Agents should load only the document needed for the current task.

## Why this exists
The goal is to reduce prompts from hundreds/thousands of tokens to a task ID.

Future prompt:

```text
Implement RAG-01.
```

or, if the tool does not automatically honor repository instructions:

```text
Implement RAG-01. Follow AGENTS.md/CLAUDE.md. Do not commit.
```

## Files
- `PROJECT_CONTEXT.md` — project architecture and invariants.
- `REPO_MAP.md` — where major code lives.
- `ENGINEERING_RULES.md` — language/framework best practices.
- `SECURITY.md` — tenancy, auth, export, observability rules.
- `TESTING.md` — exact CI-equivalent commands.
- `BENCHMARKING.md` — how to measure changes.
- `DECISIONS.md` — durable architecture choices.
- `TASK_INDEX.md` — compact task list.
- `tasks/*.md` — one small file per task. Read only the requested one.
- `TASK_TEMPLATE.md` — template for new work.
- `QUICK_PROMPTS.md` — minimal prompts to use day-to-day.
- `INSTALL.md` — one-time installation instructions.

## Source of truth
1. Current executable code and tests.
2. Current task file.
3. Architecture/security decisions here.
4. README/public docs last.

If this documentation drifts from code, the agent must report the drift and follow code unless the task is explicitly a documentation/migration task.


## Security note
Live handoff/history/bugs/debt/failed approaches are local/private under `.agent-private/`; generated index JSON is local-only. Do not commit either to the public repository.
