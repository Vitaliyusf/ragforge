# Migrate AI Brain v2 → v2.1 Secure

Do this before pushing the brain setup to a public repository.

## 1. Add to `.gitignore`

```gitignore
/docs/ai/generated/*.json
/.agent-private/
```

Do not ignore `docs/ai/generated/README.md`.

## 2. Stop tracking volatile generated indexes if already staged/tracked

```bash
git rm --cached -f docs/ai/generated/INDEX_META.json 2>/dev/null || true
git rm --cached -f docs/ai/generated/FILE_INDEX.json 2>/dev/null || true
git rm --cached -f docs/ai/generated/SYMBOL_INDEX.json 2>/dev/null || true
git rm --cached -f docs/ai/generated/ROUTE_INDEX.json 2>/dev/null || true
git rm --cached -f docs/ai/generated/IMPORT_INDEX.json 2>/dev/null || true
git rm --cached -f docs/ai/generated/CONFIG_INDEX.json 2>/dev/null || true
git rm --cached -f docs/ai/generated/FRONTEND_INDEX.json 2>/dev/null || true
```

On PowerShell, remove only files that are actually tracked/staged.

## 3. Remove operational memory from the public tree

Do not publish live:
- `docs/ai/memory/HANDOFF.md`
- `docs/ai/memory/CHANGE_HISTORY.jsonl`
- `docs/ai/memory/BUGS.json`
- `docs/ai/memory/TECH_DEBT.json`
- `docs/ai/memory/FAILED_APPROACHES.json`

Copy any history you want to preserve into a private location first.

## 4. Install/replace v2.1 files
Replace the matching v2 files with the v2.1 versions.

## 5. Create private memory

```bash
python scripts/ai/init_private_brain.py
```

## 6. Rebuild local generated indexes

```bash
python scripts/ai/rebuild_repo_brain.py
```

## 7. Validate

```bash
python scripts/ai/validate_ai_memory.py
git status --short
git diff --cached --check
```

Verify `.agent-private/` and generated JSON do NOT appear in `git status` as staged files.

## If v2 was already pushed publicly
The Git SHA / timestamp / dirty boolean alone do not justify credential rotation or Git-history rewriting.

If any actual secret, private customer data, auth token, or sensitive vulnerability detail was pushed:
1. rotate/revoke the secret first;
2. remove it from the repository;
3. decide whether history rewriting is necessary;
4. treat copies/forks/caches as potentially retained.
