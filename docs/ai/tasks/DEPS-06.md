# DEPS-06 — Canonicalize Python test dependencies

**Branch:** `chore/python-test-dependencies`

## Goal
Create one canonical Python test-tool dependency set and remove pytest tooling from service runtime requirements.

## Problem
The repository currently has conflicting test dependencies:
- `backend/requirements-dev.txt`
  - `pytest==8.2.2`
  - `pytest-asyncio==0.23.7`
  - `pytest-mock==3.14.0`
- `backend/files/requirements.txt`
  - `pytest==7.4.0`
  - `pytest-asyncio==0.21.0`
- `backend/memory/requirements.txt`
  - `pytest==7.4.3`
- other service runtime requirements generally do not own pytest.

Installing multiple service requirements into one local `.venv` can therefore downgrade/replace pytest or pytest-asyncio and produce plugin incompatibility such as:
`ImportError: cannot import name 'FixtureDef' from 'pytest'`.

## Primary scope
- `backend/requirements-dev.txt`
- new `backend/requirements-test.txt` if appropriate
- `backend/files/requirements.txt`
- `backend/memory/requirements.txt`
- `.github/workflows/ci.yml`
- Docker/dev documentation only where required

## Required behavior

### Canonical test dependencies
Create one explicit canonical test dependency set, preferably:

```text
backend/requirements-test.txt
```

It must own the repository test-runner packages, including the currently supported compatible pair for:
- pytest
- pytest-asyncio
- pytest-mock

Use versions proven compatible with the current repository tests and Python 3.11.

### Runtime requirements
- Remove pytest/test-only packages from Files and Memory production/runtime requirements unless runtime code actually imports them.
- Verify service Docker/runtime installs do not require test packages.

### CI installation
Simplify backend CI test setup so it deterministically installs:
1. base runtime dependencies
2. service runtime dependencies
3. canonical test requirements

Remove conditional logic of the form:
`import pytest || pip install ...`
once canonical test requirements are authoritative.

### Local development
Document the canonical local install path so an agent/developer does not combine conflicting pytest versions accidentally.

Do not create per-task scratch virtual environments as the normal workflow.

## Acceptance
- One canonical pytest / pytest-asyncio version pair is used for repository testing.
- Files and Memory runtime requirements no longer pin conflicting pytest packages unless technically required.
- `python scripts/ai/check.py doctor` can load pytest normally in a correctly provisioned Python 3.11 dev environment.
- Files tests pass.
- Memory tests pass.
- RAG tests pass.
- Shared tests pass if shared test tooling is affected.
- Backend CI matrix remains green.
- No `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` workaround is required.

## Validation
Use focused validation while editing.

Before finish:
- affected Files tests
- affected Memory tests
- RAG tests because the original local failure involved pytest-asyncio compatibility
- CI run is authoritative for the complete backend matrix

Do not reinstall or benchmark unrelated frontend dependencies.

## Rules
- Follow root/scoped agent instructions.
- Do not casually upgrade application/runtime libraries.
- Keep dependency changes limited to test tooling separation/compatibility.
- Do not commit or push.

## Suggested commit
**Title:** `chore(test): centralize python test dependencies`

**Description:**
- move pytest tooling into one canonical test requirements file
- remove conflicting test-only pins from service runtime requirements
- simplify CI to install the same compatible test toolchain deterministically
- prevent local pytest/pytest-asyncio drift across services
