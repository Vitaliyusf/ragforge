# Private Agent Memory Template

Do not use this file as live memory. Run:

```bash
python scripts/ai/init_private_brain.py
```

That creates gitignored `.agent-private/` with:
- HANDOFF.md
- CHANGE_HISTORY.jsonl
- BUGS.json
- TECH_DEBT.json
- FAILED_APPROACHES.json

For Claude/Codex sessions on another machine/cloud worker, use a separate private sync mechanism/repository for `.agent-private/`. Never push it to the public RAGForge repository.
