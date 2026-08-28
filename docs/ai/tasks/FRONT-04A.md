# FRONT-04A — Promote Eval to top-level navigation and redesign the Eval workspace

**Branch:** `feat/eval-top-level-workspace`

## Goal

Turn Eval into a first-class workspace next to Chat and Files, and replace the current visually dense / duplicated Eval layout with a compact, coherent benchmark workspace.

This task is primarily information architecture and frontend presentation. Preserve all existing benchmark/eval backend behavior and evidence semantics.

---

## Current UX problems to fix

The current Eval UI is nested under:

```text
Metrics → Eval
```

and inherits page chrome that is not relevant to Eval, including metrics-oriented controls.

The current page visually mixes two different run concepts:

```text
Golden set
  → Retrieval only / End-to-end
  → Run evaluation

Benchmark center
  → Profile
  → Start benchmark
```

This produces two competing primary CTAs and makes it unclear which run path should be used.

The page also has:

- excessive card height and empty space;
- controls scattered across wide cards;
- status information repeated in several places;
- a large amount of benchmark detail always visible;
- history rendered as bulky stacked rows;
- inconsistent select styling;
- the Benchmark Center currently uses a native `<select>`, which can render a light/white OS dropdown inside the dark UI;
- Eval is visually treated as a subsection of Metrics even though it is an operational workflow.

---

# PART 1 — Make Eval a top-level navigation destination

Add `Eval` to the primary navigation alongside the existing top-level destinations such as:

```text
Chat
Files
Users
Models
Logs
Health
Metrics
Eval
```

Choose the exact position based on the current nav structure, but preferred placement is:

```text
Chat · Files · Eval · Users · Models · Logs · Health · Metrics
```

or place Eval immediately next to Metrics if the current grouping is stronger.

Use the existing flask icon (`FlaskConical`) or the current Eval icon.

## Remove Eval from the Metrics secondary tabs

Metrics should keep only metrics-oriented sections such as:

```text
Overview
Latency
Retrieval
Quality
Pipeline
```

Eval must no longer appear as a Metrics sub-tab.

## Route / deep-link compatibility

Create a canonical Eval route using the repository's routing conventions.

Preserve old Eval deep links if any exist.

If an old URL such as a Metrics Eval tab is reachable, redirect or route it to the new canonical Eval page rather than producing a dead page.

Do not break browser back/forward navigation.

---

# PART 2 — Eval page header

The new page header should identify the workflow directly:

```text
Eval
Golden sets, benchmark profiles and quality diagnostics
```

Do not show the Metrics title.

Do not show the Metrics `Last 24 hours` filter on Eval.

Only show tenant/workspace context if it is meaningful for Eval and already part of the global application context; do not duplicate global workspace controls just because Metrics had them.

Keep the current visual language:

- dark background;
- subtle borders;
- rounded surfaces;
- lavender/violet accent;
- compact Lucide icons;
- current typography and CSS variables.

Do not introduce a second design system.

---

# PART 3 — Replace the current two-card hierarchy with a clearer workflow

Use this page hierarchy:

```text
Eval header

Evaluation setup
  ├─ Golden set selector
  ├─ Items
  ├─ Version / fingerprint (compact)
  ├─ Import
  └─ Dataset overflow actions

Run benchmark
  ├─ Profile selector
  ├─ concise profile summary
  ├─ Start benchmark
  └─ current/last status

Active run / latest run
  ├─ status
  ├─ current phase
  ├─ progress
  ├─ elapsed
  ├─ outcome counters
  └─ diagnostic export when terminal

Results
  ├─ summary metrics
  ├─ validation / provenance / comparison details
  └─ item drill-down

History
  └─ compact run table
```

The user should be able to understand:

```text
1. Which dataset am I using?
2. Which benchmark profile will run?
3. Is something running now?
4. What happened?
```

without scanning multiple large cards.

---

# PART 4 — Evaluation setup card

Create one compact setup surface.

Preferred desktop layout:

```text
Golden set [ golden_smoke_30 ▼ ]  30 items  v1  fingerprint…
                                      [Import] [•••]
```

Dataset metadata must not consume a full row of vertical space.

Use the existing themed `Select` component.

Move destructive actions such as Delete into an overflow/menu or clearly secondary action area.

Do not place Delete beside the primary status/metrics as if it were a common operation.

Preserve:

- item count;
- last-run information where useful;
- dataset version/fingerprint;
- drift warnings;
- import behavior;
- delete confirmation;
- tenant scoping.

---

# PART 5 — Resolve the duplicate Run Evaluation vs Start Benchmark UX

The Benchmark profile flow is the primary workflow.

Make:

```text
Start benchmark
```

the single primary CTA on the main page.

The existing ad-hoc Eval run:

```text
Retrieval only
End-to-end
Run evaluation
```

must remain available if it is still useful/functionally distinct, but demote it into one of:

```text
Advanced
Single evaluation
Quick run
More actions
```

Prefer a collapsible/secondary section or menu.

Do not delete functionality merely to simplify the visual hierarchy.

Add short copy explaining the distinction:

```text
Benchmark profile
Runs a repeatable diagnostic workflow.

Single evaluation
Runs one retrieval or end-to-end eval without the benchmark workflow.
```

Keep cost confirmation for end-to-end single evaluation.

---

# PART 6 — Redesign profile selection

Do not use a raw HTML `<select>`.

Use the application's themed Select/Popover primitives so the menu remains consistent in dark mode.

Each profile option should communicate:

```text
name
cost level
phases
```

Example compact option:

```text
Smoke Quality          Moderate
Regular E2E · 30 items
```

Profiles:

```text
Quick Retrieval
Smoke Quality
Full Quality
Extended Comparison
Full Diagnostic
```

Use existing profile semantics exactly.

Do not invent ETA values.

Do not label expensive work as free.

For Full Diagnostic / expensive profiles, use a subtle warning treatment and existing confirmation behavior.

---

# PART 7 — Active benchmark card

When a benchmark is queued/running, make the active run the visual focal point.

Use a compact state panel with:

```text
Running · Smoke Quality

Regular E2E
18 / 30 items                       60%

[==================------]

Successful        17
Guardrail blocked  1
Failed             0
In flight           4

Elapsed 2m 41s
Last progress 3s ago
```

Use the backend's persisted progress; do not fake client-side progress.

## Phase timeline

Show executable phases as a small horizontal/vertical stepper:

```text
✓ Retrieval  →  ● Regular  →  ○ Extended
```

Only include phases relevant to the selected profile.

States:

```text
completed
running
queued
partial
failed
interrupted
unsupported
skipped
```

must remain semantically distinct.

Do not represent unsupported as failed.

---

# PART 8 — Terminal run presentation

On success:

- show a compact success state;
- make `Download Diagnostic ZIP` visible;
- show summary metrics;
- keep details available without flooding the page.

On partial/interrupted:

- use warning/amber treatment;
- explain the state in text.

On failure:

- use error/red treatment;
- show concise error;
- keep diagnostic download available when the backend allows it.

Do not rely on color alone; status text/icon must be present.

---

# PART 9 — Results structure

Do not render every evidence block at full prominence.

Use progressive disclosure.

Primary results:

```text
MRR
Recall@5
Groundedness
Citation precision
Citation recall
Latency
```

only where actually measured.

Do not render an unmeasured metric as zero.

Secondary details can live under compact sections such as:

```text
Validation
Provenance
Config comparison
Failure attribution
Scores at k
Per-item details
```

Use accordions/details panels or clear subsections according to existing component conventions.

Do not hide critical warning/error evidence behind an accordion by default.

---

# PART 10 — Benchmark history

Replace bulky stacked history rows with a compact table/list.

Preferred columns:

```text
Started
Profile
Dataset
Status
Duration
Key result
Actions
```

Actions:

```text
View
Download
```

Do not expose long benchmark IDs as primary visual content.

Put the full ID in a tooltip/copy detail if needed.

Highlight the selected/current run subtly.

On narrow screens, switch to stacked compact rows.

---

# PART 11 — Spacing / visual cleanup

Use a deliberate vertical rhythm.

Preferred page width should match the existing Metrics content width.

Avoid:

- giant empty areas inside cards;
- controls separated by hundreds of pixels;
- repeated headings that say the same thing;
- too many simultaneous bordered rectangles;
- multiple equally prominent purple buttons.

There should normally be one primary CTA per major surface.

Use borders and background contrast sparingly.

---

# PART 12 — Keep existing design language

Do not introduce random new colors.

Map states to existing design tokens where possible:

```text
idle / neutral → muted
running        → violet / accent
success        → success green
partial        → warning / amber
failed         → danger / red
```

Use the same button, Badge, Card, Select, Modal and typography primitives already used elsewhere.

---

# PART 13 — Responsive behavior

Desktop:
- compact horizontal setup controls;
- profile and primary CTA aligned cleanly;
- results can use grids.

Tablet:
- controls wrap predictably.

Mobile/narrow:
- no horizontal overflow;
- primary CTA full-width only where necessary;
- history becomes stacked;
- progress remains readable.

Do not rely on hover for required information.

---

# PART 14 — Accessibility

All controls need accessible names.

Keyboard navigation must work for:

```text
top-level Eval nav
dataset select
profile select
menus
accordions
history actions
run actions
```

Focus states must remain visible.

Status must use:

```text
color + icon/text
```

not color alone.

Do not add continuous flashing/blinking in this task.

---

# PART 15 — Tests

Follow:

```text
TEST WHAT CHANGED.
LET CI TEST THE REPOSITORY.
```

Required focused frontend coverage:

1. Eval exists in top-level navigation.
2. Metrics no longer renders Eval as a secondary tab.
3. old Eval deep link redirects/resolves to canonical Eval.
4. Eval page does not render the Metrics time-window control.
5. dataset selection still works.
6. import still works.
7. delete still requires confirmation.
8. benchmark profile selector uses themed UI, not raw native select.
9. selected profile starts the correct benchmark profile.
10. expensive profile confirmation remains.
11. single/ad-hoc eval remains reachable.
12. running benchmark renders active progress state.
13. completed benchmark renders terminal summary/export.
14. failed/partial/interrupted remain visually and semantically distinct.
15. history selection/download still work.
16. unmeasured values remain `—`/unobserved, not zero.
17. responsive layout has no obvious horizontal overflow in tested widths.

Run focused Vitest.

Because this changes top-level navigation and a substantial production UI:

```text
npm run build
```

is required near completion.

Do not change backend tests unless backend files are actually touched.

---

# PART 16 — Manual acceptance after merge

Check at minimum:

```text
1440–1600px desktop
1024px tablet-ish width
mobile/narrow viewport
```

Capture screenshots of:

1. Eval idle state.
2. profile dropdown open.
3. active benchmark state.
4. completed benchmark state.
5. Metrics page showing Eval removed from secondary tabs.
6. top-level nav with Eval selected.

Manual acceptance must specifically confirm that no white/native dropdown appears in the dark interface.

---

# Out of scope

Do not implement in this task:

- animated top-nav activity indicators;
- Chat activity state;
- Files activity state;
- benchmark backend changes;
- benchmark profile semantic changes;
- new metrics;
- performance tuning;
- provenance changes.

Those belong to FRONT-04B or existing backend tasks.

---

# Acceptance criteria

```text
[ ] Eval is top-level.
[ ] Metrics no longer owns Eval UI.
[ ] Existing routes/deep links remain safe.
[ ] Eval page has a clear setup → run → progress → result hierarchy.
[ ] Only one primary benchmark CTA competes for attention.
[ ] Single/ad-hoc eval remains available but secondary.
[ ] Native profile select is removed.
[ ] Active run is visually clear.
[ ] Results/history are substantially less cluttered.
[ ] Existing evidence semantics are preserved.
[ ] Focused Vitest passes.
[ ] npm run build passes.
[ ] Manual screenshots confirm dark-theme and responsive quality.
```

---

# Final report

Return exactly:

1. UX problems fixed.
2. New Eval route/navigation structure.
3. Changed files grouped by:
   - app shell/navigation
   - Eval page
   - benchmark components
   - tests
4. Before/after information hierarchy.
5. How single eval vs benchmark is represented.
6. Themed-select/native-select fix.
7. Focused Vitest counts.
8. `npm run build` result.
9. Manual visual checks still required.
10. Known UI follow-ups.

Do not commit or push.
