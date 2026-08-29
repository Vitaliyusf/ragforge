@AGENTS.md

# Claude Code

- Treat the repository brain as navigation assistance, not proof; verify retrieved code/tests before editing.
- Prefer path-scoped rules in `.claude/rules/` over loading broad documentation.
- Use subagents for large exploratory searches only when they keep the main context smaller; return evidence paths/symbols, not search transcripts.
- Cross-agent continuity belongs in the repository memory/handoff workflow, not hidden chat state.

<!-- RAGFORGE_REPO_BOOTSTRAP_BEGIN -->
## Claude Code repo bootstrap

For Claude Code, the project hook is the enforcement layer for initial repository navigation.

- If the Repo Bootstrap gate denies a tool, run the exact bootstrap command from the denial message.
- Do **not** substitute a direct `scripts/ai/brain.py query`; the wrapper removes active-task-id bias and returns diversified source/test ownership evidence.
- Treat the bootstrap output as the first ownership map and inspect its bounded paths/ranges before broader search.
- Large source files must be read in bounded ranges; do not dump whole files.

This Claude-specific bootstrap behavior supersedes any older direct initial Brain-query wording imported from `AGENTS.md`; shared engineering, Git, testing, and finalization rules in `AGENTS.md` still apply.
<!-- RAGFORGE_REPO_BOOTSTRAP_END -->
