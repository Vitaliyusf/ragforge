# FRONT-FOUNDATION-01 — Frontend architecture and styling foundation

**Branch:** `refactor/frontend-foundation`  
**Phase:** Frontend / Product Track  
**Priority:** P1  
**Depends on:** `LLM-CTRL-01`

## Goal

Refactor the frontend foundation before major UX redesign so later product work is built on clear boundaries, reusable primitives, a coherent styling system, and measurable performance.

This task is **not** a visual redesign.

## Non-goals

- No Files redesign.
- No Chat redesign.
- No Eval redesign.
- No navigation redesign.
- No new UI framework.
- No broad rewrite.
- No mass formatting.
- No speculative state-management migration.

## Required inventory

Audit:
- frontend directory structure
- app/router boundaries
- client vs server components
- large components
- repeated components
- repeated class strings
- global CSS
- CSS modules
- inline styles
- Tailwind usage
- CVA usage
- duplicated tokens/colors/radii/spacing
- data fetching
- API client ownership
- local/global state
- effects
- motion usage
- accessibility primitives
- dead code
- production bundle/build size

Produce private evidence under `.agent-private/`.

## Architecture target

Prefer feature ownership:

```text
src/
  features/
    chat/
    knowledge/
    eval/
    metrics/
    operations/
    admin/
  components/
    ui/
    feedback/
    status/
  lib/
    api/
    formatting/
    accessibility/
  styles/
```

Do not move files mechanically. Move only when ownership becomes clearer.

## Component rules

- presentation components do not own network behavior
- data/API behavior belongs in hooks/services/server boundaries as appropriate
- no duplicated server data in multiple local states
- derived state should stay derived
- avoid `useEffect` when render/event/data-flow logic can express the behavior directly
- keep client boundaries as small as practical
- split components when one component owns unrelated responsibilities

## Styling strategy

Use the existing stack unless audit proves otherwise:

```text
Tailwind
CSS variables/design tokens
class-variance-authority
clsx
tailwind-merge
CSS Modules only when local complex styling is clearer than utilities
Motion/Framer Motion only for state/layout animation
```

Do not add:
- MUI
- Chakra
- Emotion
- styled-components
- a second utility framework

## Tailwind 4 decision

Audit Tailwind 3 → 4 once.

Migrate only if:
- supported browser baseline is acceptable;
- migration is bounded;
- existing plugins/config are compatible;
- production build/tests remain green;
- migration simplifies the actual project.

If migrated, do it in this task before redesign work.

If not, explicitly KEEP Tailwind 3 and stop reconsidering it during the frontend track.

## Design tokens

Create/normalize semantic tokens for:

```text
surface/page
surface/primary
surface/secondary
surface/elevated

text/primary
text/secondary
text/muted

border/default
border/strong

brand/primary

status/success
status/warning
status/error
status/live

radius/control
radius/surface

motion/fast
motion/normal
motion/slow
motion/easing
```

Themes should override semantic values rather than duplicate feature styles.

## Shared variants

Use CVA where it improves consistency:
- Button
- Badge
- Status
- Panel/surface
- Tabs
- form/control states

Do not abstract one-off styling prematurely.

## Shared UX states

Establish reusable patterns for:
- loading
- empty
- error
- partial
- stale/delayed
- disabled
- permission denied

## Motion policy

CSS transitions:
- hover
- focus
- color
- simple opacity

Motion library:
- drawer/panel enter-exit
- expandable rows
- shared layout transitions
- pipeline/status transitions

Respect `prefers-reduced-motion`.

No decorative infinite motion except real Running/Streaming/Processing state.

## Performance baseline

Capture:
- production build duration
- JS output/bundle evidence available from build tooling
- CSS output size
- frontend Docker image size if cheap
- dependency count
- obvious oversized client components
- obvious rerender hotspots

Do not invent numbers.

## Cleanup

Within touched scope:
- delete dead components/hooks/styles
- remove duplicate helpers
- consolidate duplicate styles/tokens
- remove obsolete CSS
- remove obsolete scripts/dependencies only when proven unused

## Validation

```text
focused component/feature tests
→ full frontend test suite once
→ production build
→ changed-file lint/type checks if configured
→ git diff --check
```

Do not run backend broad suites.

## Completion report

Report:
- architecture changes
- files moved/removed
- components/hooks/styles removed
- styling strategy decision
- Tailwind 3/4 decision
- dependencies added/removed
- bundle/CSS/build evidence
- known frontend debt intentionally deferred

STOP. Do not start CHAT-01.
