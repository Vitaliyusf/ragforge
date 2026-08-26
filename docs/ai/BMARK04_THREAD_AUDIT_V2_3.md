# BMARK-04 Codex Thread Audit

## Overall
Implementation flow appears technically serious and substantially aligned with BMARK-04:
- tenant-scoped Files-owned resolution;
- fact-to-chunk mapping;
- explicit unresolved facts;
- readiness/deleted handling;
- latest chunk-version handling;
- RAG preparation integration;
- UI warnings;
- focused + service + frontend coverage.

## Important validation caveat
The transcript is NOT a clean authoritative "all green" validation.

The RAG tests were executed with:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
```

because the installed `pytest-asyncio` / `pytest` combination could not load normally.

The transcript then reports three async tests skipped.

Therefore the correct status is:

```text
Files suite: PASS (based on transcript)
Frontend tests/build: PASS (based on transcript)
RAG synchronous/focused coverage: PASS
RAG normal full suite: BLOCKED/PARTIAL because normal pytest plugin loading was incompatible
```

Do not call the entire affected validation fully green until the RAG suite passes in a correctly provisioned environment/CI with normal plugin loading.

## Where tokens were wasted

### 1. Discovery was broader than the brain rules intended
Before editing, the agent ran many broad `rg` / `rg --files` / full-file reads across backend, frontend and memory.

The improved rules now require:
- task file first;
- one targeted brain query if task paths are insufficient;
- an initial exploration budget;
- no repo-wide source scan before targeted lookup fails.

### 2. Environment troubleshooting repeated
The agent:
- tried `check.py`;
- probed multiple interpreter paths;
- probed `uv`, `python3`, `ruff`, `npm`;
- retried with the `.venv`;
- manually changed pytest plugin behavior.

The new `check.py doctor` handles interpreter/tool probing once and reports `BLOCKED` compactly.

### 3. Pytest plugin bypass weakened validation semantics
Disabling plugin autoload let synchronous tests run, but skipped async coverage.

v2.3 explicitly forbids using plugin bypass/exclusion to manufacture a green service suite.

### 4. Temporary-directory troubleshooting cost multiple commands
Several commands created/removed custom pytest basetemp directories.

v2.3 automatically uses:

```text
.agent-private/test-tmp/<service>/
```

and manages it inside `check.py`.

### 5. Mypy scope was rerun/shrunk repeatedly
The transcript ran mypy on:
- a broad changed-file set;
- then two RAG files;
- then one RAG file.

v2.3 requires running the intended scope and fixing/reporting that scope rather than shrinking it to obtain green.

### 6. Memory finalization started before code was fully frozen
The agent updated memory, rebuilt/validated the brain, then made additional source/frontend edits and rebuilt again.

v2.3 enforces:
code validation → final diff → memory → one rebuild → one validation.

### 7. Manual handoff/history work
The agent manually inspected/wrote HANDOFF/history.

v2.3 prefers `record_handoff.py` and prohibits reading full history during normal completion.

## Expected effect
These changes cannot guarantee a specific token percentage because tool-output accounting is hidden, but they remove the clearest repeated-work clusters visible in this thread while preserving validation quality.
