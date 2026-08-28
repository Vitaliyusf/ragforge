# FILES-LIST-01 — Knowledge operations table

**Branch:** `feat/knowledge-operations-table`  
**Phase:** Frontend / Product Track  
**Depends on:** `CHAT-01`

## Goal

Replace the current document-card gallery with a scalable operational document interface that clearly communicates document state, ingestion progress, failures, and next actions.

## Primary layout

Default to a compact row/table model.

Recommended information hierarchy:

```text
Document
Type / size
Status
Pipeline
Updated
Actions
```

Ready rows stay compact.

Processing/failed rows may expand to show the active or failed stage.

## Canonical ingestion flow

Represent the real pipeline only.

Example:
```text
Upload → Extract → Chunk → Embed → Index
```

If the backend exposes more authoritative stages, use those instead.

States must come from real backend state:
- queued
- running
- completed
- failed
- skipped when applicable

Never fake percentage progress.

## Failure UX

Every failed document state should answer:

1. What happened?
2. Why?
3. What can the user do next?

Example:
```text
Embedding failed
Embedding request timed out.
Document is not searchable.
[Retry] [View trace]
```

## Document drawer

Selecting a document should expose a focused detail surface:

```text
Overview
Pipeline
Chunks
Retrieval
Activity
Actions
```

Only show data that exists.

Potential fields:
- type/size
- uploaded/indexed timestamps
- chunks/vectors
- stage durations
- last retrieval
- ingestion trace
- re-index/delete actions

## Table capabilities

Required:
- search
- status filters
- sorting
- clear result count
- row selection where bulk actions exist

Evaluate:
- pagination
- virtualization
- TanStack Table / TanStack Virtual

Do not add a table library automatically. Add it only if it materially reduces complexity and provides needed sorting/filtering/virtualization behavior.

## Bulk actions

Only expose supported operations.

Potential:
- re-index
- delete

Explain destructive/reprocessing impact before execution.

## Ready-state simplification

Do not repeat:
- Complete
- 8/8
- eight green bars

A ready document should be concise.

Example:
```text
Ready · Indexed
```

Pipeline detail can remain in the drawer.

## Activity

Replace empty decorative side panels with useful activity or hide them when empty.

Activity should describe real ingestion events/failures.

## Motion

Allowed:
- row insertion after upload
- active pipeline node
- expand/collapse
- row removal with Undo toast
- subtle progress transitions backed by state

Idle ready rows should not animate.

## Refactor touched scope

- remove obsolete card components/styles
- consolidate document status components
- move list filtering/sorting/data behavior to clear boundaries
- avoid per-row redundant API calls
- avoid full-list rerenders for local row changes when practical

## Performance acceptance

Use a synthetic/fixture set of ~1,000 documents.

Validate:
- search/filter remains responsive
- scrolling is usable
- row updates do not visibly freeze the page

If the current implementation fails, introduce pagination or virtualization and measure again.

## Tests

```text
knowledge/files focused tests
→ search/filter/sort
→ pipeline states
→ failure actions
→ drawer
→ bulk action behavior if implemented
→ 1,000-row performance sanity check
→ full frontend suite once
→ production build
→ git diff --check
```

STOP. Do not start EVAL-UX-01.
