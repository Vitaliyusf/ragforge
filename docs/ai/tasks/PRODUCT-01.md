# PRODUCT-01 — Product navigation, terminology, roles, and global activity

**Branch:** `feat/product-navigation-and-status-model`  
**Phase:** Frontend / Product Track  
**Depends on:** `EVAL-UX-01`

## Goal

Give RagForge one coherent product model instead of exposing every subsystem as an equal top-level destination.

## Product pillars

Target mental model:

```text
Workspace
  Chat
  Knowledge

Quality
  Eval
  Metrics

Operations
  Models
  Logs
  Health

Administration
  Users
  Settings
```

Implement the best-fit navigation presentation for the existing shell without a framework rewrite.

## Role-aware visibility

Navigation should reflect permission/role when authoritative role data already exists.

Example policy:

```text
Member
  Workspace

Evaluator
  Workspace + Quality

Operator
  Workspace + Quality + Operations

Admin
  all
```

Do not invent backend authorization in the frontend. UI visibility must reflect existing authorization, not replace it.

## Canonical terminology

Unify inconsistent terms such as:
- Files / Knowledge files / Document library
- Rag / RAG Orchestrator
- Vector Db / Vector DB
- Live / Ready / Healthy / Connected where semantics overlap

Define one canonical label per product concept.

## Status taxonomy

Use distinct domains.

Resource:
```text
Ready
Processing
Failed
```

Service:
```text
Healthy
Degraded
Unhealthy
```

Execution:
```text
Queued
Running
Completed
Partial
Failed
Skipped
```

Connectivity:
```text
Connected
Disconnected
```

Review:
```text
Passed
Needs review
Failed
```

Do not mix status domains.

## Global Activity

Replace vague duplicated `Live` badges with one top-level activity/status control.

Idle:
```text
Ready
```

Active:
```text
3 active
```

Degraded:
```text
Degraded
```

Popover may show real active work:
- answer generation
- indexing
- evaluation

Never synthesize work that the backend does not expose.

The logo/status dot may reflect the state, but status must also have text/icon and must not rely on color alone.

## Refactor touched scope

- consolidate nav definitions
- consolidate service display names
- consolidate status rendering
- remove duplicate Live indicators
- remove dead navigation/status styles

## Tests

```text
navigation grouping tests
→ permission/role visibility tests where supported
→ terminology/status tests
→ global activity state tests
→ full frontend suite once
→ production build
→ git diff --check
```

STOP. Do not start OBS-UX-01.
