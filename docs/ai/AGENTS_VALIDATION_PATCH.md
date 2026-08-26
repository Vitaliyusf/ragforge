# Paste these sections into root `AGENTS.md`

Replace the existing validation/final-response rules with the following.

## Validation strategy
Use progressive validation and minimize command output.

### During implementation
- Run `python scripts/ai/check.py fast <service> ...`.
- Check only changed files and focused regression/unit tests.
- Do not create a fresh isolated dependency environment for normal iterations.
- Do not repeatedly run full service/repository suites while coding.
- Run mypy only when typed contracts/schemas changed, the module is already covered, or the task requires it.

### Before finishing a task
- Run `python scripts/ai/check.py service <service>`.
- If frontend production behavior changed, include `--build`.
- Run broader suites only when shared contracts/infrastructure changed or the task explicitly requires them.

### Full validation
Use `python scripts/ai/check.py full --fail-fast` only for repo-wide/shared changes or final manual release/PR verification.
CI is the authoritative clean-environment validation.

### Output discipline
- Passing checks must emit only compact PASS summaries.
- On failure, show only the relevant error/tail.
- Never dump dependency installation/resolution logs into agent context.

## Final response
Return:
1. Branch/effective worktree.
2. Changed files.
3. 3–7 implementation bullets.
4. Tests/checks and results.
5. Shared-memory records updated (IDs only).
6. Risks/unverified items.
7. **Copy-paste Git commit title.**
8. **Copy-paste Git commit description/body.**

The Git output must always use this format:

```text
Commit title:
<Conventional Commit title, max ~72 chars>

Commit description:
<2–6 concise bullets describing what changed, why, important tests/compatibility notes>
```

Commit title must follow Conventional Commits, e.g.:
- `feat(eval): add tenant-scoped file label resolution`
- `fix(rag): globally rank pass2 retrieval candidates`
- `refactor(memory): centralize agent mutation policy`
- `chore(ai): optimize agent validation workflow`

Do not commit or push.
