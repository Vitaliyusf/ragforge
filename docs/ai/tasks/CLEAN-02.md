# CLEAN-02 — Restore repo-wide Ruff green

**Branch:** `chore/ruff-cleanup`

## Goal
Remove the current pre-existing Ruff failures so unrelated PRs do not receive a red CI result from known lint debt.

## Problem
Repo-wide CI Ruff currently fails on issues outside the benchmark changes:
- `backend/llm_agent/app/llm/implementations/vllm.py`
  - unused local variable (`F841`)
- `backend/memory/app/services/chat_exit_service.py`
  - module-level imports not at top of file (`E402`)

These failures make otherwise-correct PRs appear broken and can hide new lint regressions.

## Primary scope
Only the files currently reported by repo-wide Ruff:
- `backend/llm_agent/app/llm/implementations/vllm.py`
- `backend/memory/app/services/chat_exit_service.py`

Expand scope only if current Ruff output proves an additional existing error is required.

## Required behavior
- Fix the Ruff errors without changing runtime behavior.
- Do not suppress the rules globally.
- Do not add blanket `# noqa` unless a specific import-order pattern is technically required and clearly documented.
- Preserve imports, initialization ordering, side effects, and service behavior.
- Remove the unused variable only if it is genuinely unused; otherwise use it in the intended logic.

## Acceptance
- `ruff check backend/` passes on the branch.
- Focused tests for touched llm_agent/memory behavior pass.
- No unrelated refactor.
- No behavior change unless a latent bug is discovered; if so, stop and report before broadening scope.

## Validation
During implementation:
- Ruff only on the two changed files.
- Focused tests for the touched modules/services.

Near completion:
- `ruff check backend/` once, because this task specifically exists to restore repo-wide Ruff green.
- Do not run every backend service suite unless the code changes prove it necessary.

## Rules
- Follow root and scoped agent instructions.
- Treat this as behavior-neutral cleanup.
- Do not commit or push.

## Suggested commit
**Title:** `chore: restore repo-wide ruff checks`

**Description:**
- remove the current unused-variable and import-order lint failures
- preserve llm-agent and memory-service behavior
- restore the repo-wide Ruff CI gate without suppressing rules
