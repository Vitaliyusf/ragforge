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

Prefer targeted Repo Brain retrieval:

```bash
python scripts/ai/brain.py query "<task or symptom>" --top 12
```

Read private files directly only when the task needs their complete state:
- continuation → `.agent-private/HANDOFF.md`;
- architecture decision → matching `DECISIONS.json` entry;
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
→ sync Repo Brain v4 once
→ rebuild legacy JSON indexes once when required
→ validate memory/context once
→ final response
```

If code changes after handoff creation, the handoff was premature: validate the code first, then replace the final memory state once.

## Handoff/history
Prefer:

```bash
python scripts/ai/record_handoff.py ...
```

Keep summaries short and technical. Do not manually rewrite complete history unless the helper cannot represent the state.

## Public registry updates
Update `CAPABILITIES.json`, `SERVICES.json`, `CONTRACTS.json`, `DECISIONS.json` only when a task changes durable canonical behavior.

Do not touch public memory merely because files changed. Search existing capability/symbol/contract ownership first and update the authoritative record instead of creating a parallel owner.

Temporary compatibility records require a concrete removal condition and tracking task and must be deleted when the supported production path is retired.

## Security vulnerability rule
Unfixed vulnerability details are private by default. Never commit exploit details, vulnerable endpoints, credentials, customer impact or reproduction payloads to the public repository.

## Evidence
Use safe evidence:
- repo-relative source path/symbol;
- test name;
- task ID;
- sanitized benchmark ID;
- eventual PR/commit.

## Final validation

```bash
python scripts/ai/brain.py sync
python scripts/ai/brain.py doctor
python scripts/ai/rebuild_repo_brain.py
python scripts/ai/validate_ai_memory.py
python scripts/ai/validate_agent_context.py
```

Run this final sequence once after code and memory are stable. The legacy JSON rebuild remains during migration because existing tooling/tests still consume it; Brain v4 is the preferred interactive query path.
