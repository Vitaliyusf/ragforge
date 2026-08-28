# FRONT-POLISH-01 — Frontend production polish and portfolio readiness

**Branch:** `refactor/frontend-production-polish`  
**Phase:** Frontend / Product Track  
**Depends on:** `OBS-UX-01`

## Goal

Perform the final production-quality frontend pass after architecture, information hierarchy, and workflows are stable.

This task must not redesign the product again.

## Accessibility

Validate/fix:
- keyboard navigation
- visible focus
- semantic headings/tables
- accessible dialog/drawer focus management
- status not conveyed only by color
- aria labels
- aria-live where appropriate for streaming/ingestion
- reduced motion
- contrast

## Responsive behavior

Target desktop/laptop first.

Validate at representative widths such as:
- wide desktop
- 1366px laptop
- ~1024px

Avoid nested scrolling except where it is the actual product surface (for example logs).

## State completeness

Review all major screens for:
- loading
- empty
- partial
- stale/delayed
- error
- permission denied
- destructive action
- retry/recovery

## Destructive actions

Explain impact.

Examples:
- delete document
- re-index
- delete conversation
- disable user
- switch runtime/model when applicable

Use Undo where safe and appropriate.

## Notifications

Create/normalize toast behavior:
- short success
- actionable error
- persistent critical failure when appropriate
- no modal for routine success

## Motion final pass

Principle:

> Alive when work is happening; calm when healthy and idle.

Remove:
- decorative perpetual animations
- excessive glows
- unnecessary page transitions

Keep:
- subtle real-state activity
- drawers
- list insertion/removal
- pipeline state transitions
- focused chart transitions

## Surface/density

Normalize:
- surface hierarchy
- card nesting
- border/radius use
- typography
- desktop density by screen type

Suggested density:
- Chat: comfortable
- Knowledge/Users/Models: standard
- Logs/Eval/Metrics: dense

## Demo workspace

Provide a safe portfolio/demo path if compatible with repository architecture.

Target demo content:
- example documents
- one conversation
- one evaluation run
- one trace
- one intentional failure example

Never ship secrets or real user data.

If seeded demo data would contaminate production behavior, provide an explicit development/demo-only loader instead.

## Final evidence

Capture:
- frontend dependency count
- production build duration
- CSS output size
- JS output evidence available
- frontend image size if cheap/repeatable
- custom CSS LOC
- dead components/hooks/styles removed
- Lighthouse/accessibility results if tooling is reliable
- any measured long-list/chat responsiveness evidence

Do not invent values.

## Validation

```text
affected focused tests
→ full frontend suite once
→ production build
→ accessibility checks
→ representative responsive/manual smoke
→ git diff --check
```

## Completion report

Include:
- major UX changes
- architecture cleanup
- styling strategy
- accessibility improvements
- performance evidence
- dependencies added/removed
- intentionally deferred frontend work
- resume/interview evidence

STOP. Do not start TYPES-01.
