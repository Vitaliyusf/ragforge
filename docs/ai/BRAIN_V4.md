# RAGForge Repo Brain v4

Repo Brain v4 is a **local-first, zero-service** navigation layer for Codex and Claude Code.
It intentionally uses Python stdlib + SQLite FTS5 + Python AST + Git so a clean clone does not need Docker, Qdrant, an embedding server, or external APIs to understand the repository.

## Storage

Private generated state lives at:

```text
.agent-private/brain/brain.sqlite3
```

It is never committed.

The database stores:
- source/document chunks;
- exact symbols and paths;
- BM25 full-text index;
- lightweight structural edges (calls/imports/routes/references);
- source authority (`authoritative`, `task`, `source`, `history`);
- repository HEAD/freshness metadata;
- selected private operational memory from `.agent-private/`.

## Commands

```bash
python scripts/ai/brain.py sync
python scripts/ai/brain.py status
python scripts/ai/brain.py doctor
python scripts/ai/brain.py query "<task-id or code concept>" --top 12
python scripts/ai/brain.py query "<exact symbol or route>" --top 12 --json
python scripts/ai/brain.py context "<implementation goal>" --top 10 --budget-chars 12000
```

`sync` is incremental by file size + mtime and hashes changed content before replacing chunks. `--full` forces a complete rebuild.

## Retrieval

Query ranking fuses:
1. exact path/symbol/task matches;
2. SQLite FTS5 BM25 results;
3. source-authority preference;
4. bounded structural expansion from calls/imports/tests.

This is deliberately deterministic and dependency-free. Semantic embeddings are an optional future layer and should only be added when repository retrieval evals show a measurable recall/context-yield gap.

## Compatibility

`scripts/ai/brain_query.py` remains as a compatibility wrapper, so existing commands such as:

```bash
python scripts/ai/brain_query.py "<task-id or goal>" --top 12
```

use Brain v4 without changing agent prompts.

The existing `rebuild_repo_brain.py` JSON indexes remain available during migration; Brain v4 does not require deleting them.

## Design rules

- The brain is navigation assistance, never authority over current code/tests.
- Generated state is private and disposable; `sync --full` can recreate it.
- No network call is required.
- No production datastore is reused.
- No user/customer document content is indexed beyond repository/private-agent files explicitly enumerated by the tooling.
- Retrieval output is bounded and excerpted to avoid flooding agent context.
