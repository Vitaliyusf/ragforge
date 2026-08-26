# Security Audit — RAGForge AI Brain v2

## Result
The original v2 pack contained no embedded credentials/private keys/tokens and the Python/Bash files parsed successfully.

However, four design risks were found and are corrected in v2.1:

### HIGH — Public operational memory
RAGForge is a public repository. Tracking `BUGS.json`, `TECH_DEBT.json`, `FAILED_APPROACHES.json`, `HANDOFF.md` and `CHANGE_HISTORY.jsonl` can disclose unresolved vulnerabilities, internal work history, branch names or future sensitive findings.

**v2.1:** operational memory moved to gitignored `.agent-private/`.

### MEDIUM — Over-broad Claude Bash allow rules
Original `.claude/settings.json` allowed wildcard `git branch`, `git switch`, `git checkout`, test/build commands. `git checkout`/`switch -f`/branch deletion can destroy local work, and repository-controlled test/build commands execute repository code.

**v2.1:** only narrow read-only Git commands are auto-allowed. Destructive/write-capable commands are denied; tests/build require normal approval.

### LOW/MEDIUM — Generated index metadata
Original generated `INDEX_META.json` stored exact generation timestamp, Git SHA, branch and dirty state. Git SHA is not a secret in a public repository, but branch/timestamp/dirty metadata is unnecessary, noisy and can disclose private branch naming/work state.

**v2.1:** generated indexes are local/gitignored and `INDEX_META.json` contains only deterministic source fingerprint + counts.

### MEDIUM — Operational memory could persist raw sensitive text
Original handoff/history helper accepted arbitrary free text and wrote it to tracked memory.

**v2.1:** handoff/history is private/gitignored, common secret formats are redacted, file paths must be repository-relative, and the memory protocol forbids raw user/document/log/credential content.

## Script execution audit
- `brain_query.py`: read-only search; no shell execution.
- `rebuild_repo_brain.py`: reads repository text; writes only `docs/ai/generated/*.json`; does not import/execute indexed Python/JS.
- `validate_ai_memory.py`: read-only validation.
- `record_handoff.py`: writes only `.agent-private/`; fixed Git metadata subprocess arguments; no `shell=True`.
- `init_private_brain.py`: writes only `.agent-private/`; refuses unless Git ignores it.
- installer scripts copy package files and should not be run over an existing customized setup without reviewing diffs.

## Secret scan
No matches were found for common patterns including:
- private key PEM blocks
- GitHub PATs
- OpenAI-style keys
- AWS access keys
- JWTs
- Bearer tokens
- common secret assignments

This does not prove absence of every possible secret format. The validator provides an additional guardrail, but human review remains required before publishing.
