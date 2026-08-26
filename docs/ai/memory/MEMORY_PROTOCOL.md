# Shared Memory Update Protocol — Security-Hardened

## Data classification

### Public-safe tracked memory
Only sanitized architecture facts, capability locations, contracts and durable decisions that are safe to publish.

### Private operational memory
Write these only to `.agent-private/`:
- handoff/history
- known bugs
- technical debt
- failed approaches
- unreleased incident/root-cause details
- security findings

## Never persist in either memory
- passwords, API keys, cookies, session/auth tokens, private keys
- raw `.env` values
- raw customer/user documents or prompts
- personal/customer email addresses unless explicitly required and approved
- raw production logs containing identifiers/tokens
- secrets copied from command output
- absolute local paths containing usernames/home directories
- raw user text when a neutral technical paraphrase is enough

## Before work
1. If continuing prior work, read `.agent-private/HANDOFF.md` if it exists.
2. Search relevant public decisions/capabilities/contracts.
3. Search `.agent-private/BUGS.json`, `TECH_DEBT.json`, `FAILED_APPROACHES.json` if present.
4. Query the brain before creating a new implementation.
5. Refresh generated indexes if missing/stale.

## After meaningful write work
Always:
1. Run relevant tests/checks.
2. `python scripts/ai/rebuild_repo_brain.py`
3. Update `.agent-private/HANDOFF.md`.
4. Append one compact line to `.agent-private/CHANGE_HISTORY.jsonl`.
5. `python scripts/ai/validate_ai_memory.py`

Conditionally:
- public-safe durable architecture decision → `docs/ai/memory/DECISIONS.json`
- security-sensitive/private decision → private memory, not tracked
- unresolved bug → `.agent-private/BUGS.json`
- technical debt → `.agent-private/TECH_DEBT.json`
- failed/rejected approach → `.agent-private/FAILED_APPROACHES.json`
- new canonical capability → `CAPABILITIES.json`
- changed service/contract → `SERVICES.json` / `CONTRACTS.json`

## Security vulnerability rule
Unfixed vulnerability details are private by default. Do not commit exploit details, vulnerable endpoints, credentials, customer impact, or reproduction payloads to a public repository.

## Evidence
Every record requires safe evidence: source-relative path/symbol, test name, task ID, sanitized benchmark ID or eventual PR/commit.

## Handoff
Do not copy chat transcripts. Use short technical paraphrases. Never include raw secrets/logs.

## Decisions / failed approaches
Accepted decisions remain authoritative until superseded or a documented revisit condition is met.
Do not retry a failed approach unless a revisit condition is true or the user explicitly requests reevaluation.
