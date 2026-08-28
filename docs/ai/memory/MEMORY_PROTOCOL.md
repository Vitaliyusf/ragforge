# Shared Memory Update Protocol — Security-Hardened and Low-Noise

## Classification

### Public-safe tracked memory
Only sanitized durable project knowledge:
- service ownership;
- canonical capabilities;
- contracts;
- architecture decisions;
- stable gotchas/current-state facts.

### Private operational memory
Write only to gitignored `.agent-private/`:
- handoff/history;
- unresolved bugs;
- technical debt;
- failed approaches;
- unreleased incident/root-cause/security details.

## Never persist
- passwords/API keys/cookies/session tokens/private keys;
- raw `.env` values;
- raw customer/user documents or prompts;
- raw production logs with identifiers/tokens;
- secrets copied from command output;
- absolute local paths containing usernames/home directories when a repo-relative path is enough;
- chat transcripts.

## Read policy
Do not load all memory on every task.

Read only when relevant:
- continuation → `.agent-private/HANDOFF.md`;
- architecture decision → `DECISIONS.json`;
- known bug/debt → matching private registry;
- failed approach → matching private registry.

Do not read full `CHANGE_HISTORY.jsonl` for normal work.

## Write timing
Do not update memory while implementation is still moving.

Required order:

```text
code complete
→ focused tests
→ required domain/static checks
→ affected service tests when justified
→ final diff review
→ no more source/test edits
→ record handoff once
→ rebuild brain once
→ validate memory once
→ final response
```

Do not run `record_handoff.py`, `rebuild_repo_brain.py` or
`validate_ai_memory.py` before this point. If code changes after handoff creation,
the handoff was premature: validate the code first, then replace the memory state
once at the end. Do not perform duplicate handoff/rebuild cycles.

## Handoff/history
Prefer:

```bash
python scripts/ai/record_handoff.py ...
```

Do not manually read and rewrite full handoff/history unless the helper cannot represent the required state.

Keep summary short and technical.

## Public registry updates
Update `CAPABILITIES.json`, `SERVICES.json`, `CONTRACTS.json`, `DECISIONS.json` only when the task creates/changes durable canonical behavior.

Do not touch public memory merely because files changed.

Before recording a new capability, search the capability registry, symbols and direct
callers. Update the authoritative capability record instead of creating a parallel owner.
Configuration records describe implemented effective behavior only. Temporary compatibility
records must include a concrete removal condition and tracking task and must be deleted when
the supported production path is retired.

## Security vulnerability rule
Unfixed vulnerability details are private by default.
Never commit exploit details, vulnerable endpoints, credentials, customer impact or reproduction payloads to the public repository.

## Evidence
Use safe evidence:
- repo-relative source path/symbol;
- test name;
- task ID;
- sanitized benchmark ID;
- eventual PR/commit.

## Final validation

```bash
python scripts/ai/rebuild_repo_brain.py
python scripts/ai/validate_ai_memory.py
```

Run this final pair once after memory is stable.
