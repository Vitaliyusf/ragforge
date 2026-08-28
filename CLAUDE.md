@AGENTS.md

# Claude Code

- Treat the repository brain as navigation assistance, not proof; verify retrieved code/tests before editing.
- Prefer path-scoped rules in `.claude/rules/` over loading broad documentation.
- Use subagents for large exploratory searches only when they keep the main context smaller; return evidence paths/symbols, not search transcripts.
- Cross-agent continuity belongs in the repository memory/handoff workflow, not hidden chat state.
