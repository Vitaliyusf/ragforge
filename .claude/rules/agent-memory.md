---
paths:
  - "AGENTS.md"
  - "CLAUDE.md"
  - ".claude/**/*"
  - "docs/ai/**/*"
  - "scripts/ai/**/*"
---
# Agent-memory rules

- Keep always-loaded instructions short; procedures belong in targeted docs/rules.
- Public tracked memory contains sanitized durable project knowledge only.
- Handoffs, unresolved bugs/debt, failed approaches, and operational history stay under gitignored `.agent-private/`.
- Never persist credentials, raw customer content, production tokens/logs, or chat transcripts.
- Current code and canonical runtime docs outrank historical memory.
