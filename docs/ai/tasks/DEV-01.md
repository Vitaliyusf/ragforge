# DEV-01 — Align local agent Python environment with CI

**Branch:** `chore/dev-python-alignment`

## Goal
Make the repository's local agent/developer validation fail fast when Python or test tooling drifts from the CI-supported environment.

## Problem
CI targets Python 3.11, while a local repository `.venv` was created with Python 3.12.11 and contained an incompatible pytest/pytest-asyncio combination. This caused agents to spend many commands diagnosing an environment problem that CI did not have.

## Primary scope
- `scripts/ai/check.py`
- `docs/ai/TESTING.md`
- `.python-version` only if CI-02 has not already added it

## Required behavior

### Doctor
`python scripts/ai/check.py doctor` must clearly report:
- selected interpreter path
- selected Python major/minor
- expected repository Python major/minor
- Ruff availability/version
- pytest import/plugin-loading health
- mypy availability/version

If Python major/minor differs from the repo-supported version:
- report a clear warning or BLOCKED state according to project policy;
- do not silently continue as if environments are equivalent.

### Environment troubleshooting policy
- A blocked doctor prevents repeated automatic interpreter/plugin probing.
- Do not disable pytest plugin autoload to manufacture a PASS.
- Do not create an isolated scratch environment automatically.
- Provide one concise remediation hint pointing to the canonical Python/test requirements.

### Token/output discipline
- PASS output stays compact.
- BLOCKED output includes only the first actionable traceback/error tail.
- No dependency-resolution transcript.

## Acceptance
- Correct Python 3.11 environment produces a compact PASS doctor result.
- Wrong Python major/minor is explicitly detected.
- Broken pytest plugin loading produces `BLOCKED`.
- Doctor does not mutate/install dependencies.
- Existing focused/affected/full check modes remain backward compatible.

## Validation
- Unit-test or directly exercise doctor logic with:
  - expected Python version
  - simulated mismatched version
  - simulated pytest import/plugin failure
- No broad application test suite is required unless `check.py` changes execution semantics beyond doctor.

## Rules
- Follow root agent instructions.
- Do not make the helper auto-install packages.
- Do not commit or push.

## Suggested commit
**Title:** `chore(ai): detect local python and pytest drift`

**Description:**
- make agent doctor validate the repository Python version and pytest health
- fail fast on local environment drift instead of probing repeatedly
- keep validation output compact and non-mutating
