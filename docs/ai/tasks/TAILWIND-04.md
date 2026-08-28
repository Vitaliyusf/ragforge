# TAILWIND-04 — Tailwind 4 migration and frontend-wide CSS cleanup

**Branch:** `refactor/tailwind4-frontend-cleanup`  
**Phase:** Frontend / Product Track  
**Priority:** P1  
**Depends on:** `FRONT-FOUNDATION-01`  
**Status:** Completed — retained as canonical task record

## Goal

Migrate Tailwind 3.4.x → Tailwind 4.3.x while preserving product behavior, simplifying the CSS/tooling architecture, and performing the final frontend-wide dead-code/CSS cleanup before domain-scoped frontend tasks.

## Target state

```text
Tailwind 4.3.x
@tailwindcss/postcss
CSS-first @theme / @theme inline
explicit source discovery where required
no tailwind.config.js
no autoprefixer
one semantic token system
```

## Non-goals

- No React runtime refactor.
- No Next routing/cache redesign.
- No Chat/Files/Eval/Observability redesign.
- No broad visual redesign.
- No new UI framework.
- No mass formatting.

## Required baseline

Capture once:

- Tailwind/PostCSS versions
- JS/CSS output bytes/files
- runtime/dev dependency count
- production files/LOC
- `globals.css` LOC
- `tailwind.config.js` LOC
- full test count
- `'use client'` count
- `useEffect` count
- Framer Motion importers

Evidence:

`.agent-private/tooling/TAILWIND-04/`

## Migration contracts

### CSS entrypoint

```css
@import "tailwindcss";
```

### Theme ownership

```text
:root/.dark = runtime semantic values
@theme / @theme inline = Tailwind-facing aliases
```

Use `@theme inline` when utilities must continue resolving runtime CSS variables across `.dark`.

### Source discovery

A green Next build is not sufficient proof that Tailwind emitted application utilities.

The CSS integration test must compile `globals.css` and prove representative utilities from real application source are emitted.

### Borders

Preserve RagForge semantic default borders rather than Tailwind 4 `currentColor` behavior.

Prefer one centralized compatibility contract over mechanical edits to hundreds of call sites.

### Rings/focus

Preserve semantic focus-ring behavior and forced-colors accessibility.

### Radius/shadow/blur

Preserve the application scale; do not silently inherit changed Tailwind 4 defaults.

### Alpha modifiers

Classify semantic slash-opacity usage:

```text
INTENDED_ALPHA
ACCIDENTAL_NOOP
REDUNDANT
```

Previously ineffective Tailwind 3 classes must not silently become active and repaint the application.

### Dark mode

`.dark` remains application-controlled. Do not switch to OS `prefers-color-scheme` semantics.

## Cleanup ownership

This is the **last frontend-wide cleanup scan**.

Audit once:

- zero-import production files
- dead exports/hooks
- dead CSS/keyframes/custom properties
- obsolete compatibility files
- duplicate semantic maps/helpers
- package usage

Delete only with evidence.

Later tasks must not repeat the broad scan.

## React / Next boundaries

Do not perform:

```text
React Compiler
useEffectEvent
broad useEffect cleanup
'use client' boundary redesign
Activity rollout
Next caching/navigation
```

These belong to `REACT-19-01` and `NEXT-16-01`.

## Validation

```text
focused Tailwind migration tests
→ affected frontend tests
→ full frontend suite once
→ Next production build
→ inspect emitted production CSS
→ configured static/type checks if any
→ git diff --check
```

Production CSS must prove:

- real application utilities
- semantic utilities
- `.dark` tokens
- custom application utilities

If no visual regression stack exists, report:

```text
automated visual regression: unavailable
```

Do not install one solely for this task.

## Metrics

Report before/after where comparable:

```text
Tailwind version
tailwind.config.js LOC
PostCSS plugins
runtime dependencies
dev dependencies
production files/LOC
globals.css LOC
compiled CSS bytes/files
compiled JS bytes/files
'use client'
useEffect
Framer Motion importers
test files/test count
```

Do not claim build-speed improvement from cache-warm/noisy measurements.

## Execution rules

- Current source wins.
- Preserve unrelated dirty files.
- Never reset/stash/revert/clean.
- Prefer a dedicated frontend worktree.
- No backend changes.
- No commit/push unless explicitly requested.
- Do not use `git add .` in a shared dirty worktree.

## Closeout

```text
NO MORE SOURCE EDITS
→ record one TAILWIND-04 handoff
→ update frontend metrics evidence
→ rebuild repo brain once
→ validate repo brain once
→ STOP
```

Do not start `REACT-19-01`.
