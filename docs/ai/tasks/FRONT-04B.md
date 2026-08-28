# FRONT-04B — Global activity indicators for Eval, Chat and Files

**Branch:** `feat/global-activity-nav`

## Goal

Add subtle, polished, trustworthy activity indicators to the primary navigation so users can see when long-running work is happening even after navigating away from the feature.

Initial features:

```text
Eval
Chat
Files
```

The effect must fit the existing dark RAGForge design and must not turn the navigation into a flashing notification bar.

---

## Design principle

Do **not** blink the entire nav label.

Preferred visual language:

```text
running
→ accent-colored icon
→ small status dot / soft halo
→ thin animated activity rail under the nav item

success
→ brief green check/halo micro-animation
→ then static unseen-success dot

warning/partial
→ amber static indicator

failed
→ red status dot/icon
→ no aggressive infinite flashing
```

Text remains readable and stable.

The status should feel closer to a deployment/build indicator than a loading spinner pasted onto every tab.

---

# PART 1 — Shared activity state model

Create a small shared frontend activity model.

Minimum state vocabulary:

```text
idle
queued
running
success
warning
failed
```

Feature adapters may map backend states into it.

Example Eval mapping:

```text
queued       → queued
running      → running
completed    → success
partial      → warning
interrupted  → warning
failed       → failed
```

Do not collapse partial into success.

Do not use string comparisons scattered across nav components; centralize mapping.

---

# PART 2 — Activity metadata

A feature activity entry may contain bounded metadata such as:

```text
feature
state
label
startedAt
completedAt
progress
count
message
```

Examples:

```text
Eval
running
"Regular E2E"
18 / 30

Files
running
"Indexing 2 files"

Chat
running
"Generating response"
```

Do not put raw prompts, file contents, user messages or secrets in global activity state.

---

# PART 3 — Eval activity source

Eval state must be derived from server-backed benchmark/eval truth.

Reuse existing benchmark state and polling whenever possible.

Do not create two independent 3-second polling loops for the same benchmark just because both the Eval page and nav need status.

Preferred architecture:

```text
shared Eval activity controller/provider
        ↓
Eval page
Top navigation
```

or expose the existing benchmark hook through a shared provider.

If route navigation unmounts the Eval page, the top-level provider must continue to know about the active server-side benchmark.

On app reload/reopen, restore active Eval activity from the existing tenant-scoped benchmark history/list API if the API supports this safely.

Do not invent a fake running state from local timers.

Do not add high-frequency polling when no benchmark is active.

---

# PART 4 — Chat activity source

Map existing Chat lifecycle into global activity:

```text
request submitted / generation begins → running
stream ends successfully              → success
request/stream error                  → failed
idle                                  → idle
```

Do not persist green success forever for Chat; Chat is high frequency.

Recommended Chat terminal behavior:

```text
success animation ~0.8s
success state visible ~2–3s
then idle
```

Failure may remain visible until Chat is visited or another successful request clears it.

Do not change the actual streaming protocol.

---

# PART 5 — Files activity source

Use existing file workflow state.

Aggregate active work such as:

```text
uploading
extracting
chunking
embedding
indexing
processing
```

into `running`.

Where trustworthy, display a small count:

```text
2
```

for two active files.

On completion:

```text
brief success animation
then unseen success indicator until Files is visited
```

On failure:

```text
red failure indicator
optional bounded failed count
```

Do not fabricate pipeline phase progress if the backend does not expose it.

---

# PART 6 — Nav visual states

Keep nav item geometry stable so state changes do not shift layout.

## Idle

Current nav appearance.

No dot, rail or animation.

## Queued

- small accent dot;
- very slow opacity breath;
- optional tooltip: `Queued`.

## Running

Preferred combination:

1. icon changes to accent color;
2. 5–6px accent dot near label/icon;
3. soft halo pulse using opacity/box-shadow;
4. 1–2px activity rail under the nav item with a subtle moving gradient.

Do not animate the entire background.

Do not blink text opacity.

## Success

On transition into success:

- change status icon/dot to green;
- one micro `check-pop` / halo animation, about 500–900ms;
- no infinite green pulsing.

For Eval and Files, retain a small static green unseen-success dot until the user visits the relevant feature or a defined acknowledgement action occurs.

## Warning

Use amber:

- static amber dot/icon;
- text/tooltip identifies partial/interrupted state.

## Failed

Use red:

- static red indicator;
- optional one-time short emphasis animation;
- persist until visited/acknowledged.

Do not infinite-flash red.

---

# PART 7 — Tooltips / accessible status text

Hover/focus should be able to reveal concise state text.

Examples:

```text
Eval — benchmark running · 18/30 · Regular E2E
Eval — benchmark completed
Files — indexing 2 files
Files — 1 file failed
Chat — generating response
Chat — last request failed
```

Use bounded text.

Add accessible status to the nav item's `aria-label` or equivalent.

Do not rely on the tooltip as the only source of status.

---

# PART 8 — Unseen terminal state

Implement an acknowledgement policy.

Preferred:

```text
Eval:
  success/warning/failed persists until Eval is opened.

Files:
  success/failure persists until Files is opened.

Chat:
  success auto-clears after a short TTL.
  failure persists until Chat is opened or a later success occurs.
```

Do not permanently store stale success dots.

If persistence across full page reload is introduced, keep it minimal and let server truth override stale client state.

---

# PART 9 — Motion / accessibility

All animation must respect:

```css
@media (prefers-reduced-motion: reduce)
```

Under reduced motion:

```text
running → static accent dot + icon
success → static green check/dot
warning → static amber indicator
failed  → static red indicator
```

No movement is required to understand the state.

Never use color as the only differentiator.

Use:

```text
color + icon/dot + status text/aria label
```

Avoid rapid blinking/flashing.

Prefer CSS opacity/transform/box-shadow animations rather than JS animation loops.

---

# PART 10 — Animation tokens

Centralize animation timing/styles.

Conceptual tokens:

```text
activity-breathe: 1800–2400ms ease-in-out infinite
activity-rail:    1400–2000ms linear infinite
success-pop:       500–900ms ease-out once
failure-emphasis:  300–500ms once
```

Do not scatter arbitrary keyframes across feature components.

Use current accent/success/warning/danger CSS variables.

---

# PART 11 — Avoid unnecessary network load

A nav animation must not create backend traffic by itself.

Rules:

- no polling for Chat animation;
- no polling for Files if existing state/event data is already available;
- Eval polling only while an active server-side job is known or during a bounded restore check;
- reuse existing requests/state where possible;
- document any new polling interval.

Do not add per-tab polling loops that continue forever in idle state.

This is important because benchmark performance experiments must not acquire unnecessary background load.

---

# PART 12 — Navigation behavior

Clicking a nav item with an unseen terminal state should:

1. navigate normally;
2. allow the feature page to render the authoritative result/error;
3. acknowledge/clear the unseen nav marker according to feature policy.

Do not clear failure merely on hover.

Do not clear a running indicator on navigation.

---

# PART 13 — Suggested visual treatment for current RAGForge nav

The existing nav uses dark rounded pills and a violet selected state.

Keep that.

Recommended running state:

```text
[ flask icon ] Eval  •
──────────────────────
      moving 2px accent rail
```

The dot should be subtle enough that the selected-tab treatment remains dominant.

For an inactive tab with background work:

```text
Eval •
```

plus the rail/halo communicates activity without forcing the user into that page.

For the currently selected active tab, avoid double emphasis: retain selected background and reduce halo strength.

---

# PART 14 — Tests

Required focused coverage:

## Shared activity model

1. idle maps correctly.
2. queued maps correctly.
3. running maps correctly.
4. completed maps to success.
5. partial/interrupted map to warning.
6. failed maps to failed.
7. acknowledgement clears only terminal unseen state.

## Eval

8. active benchmark makes Eval nav `running`.
9. navigating away does not lose active Eval state.
10. completed benchmark transitions to success.
11. failed benchmark transitions to failed.
12. opening Eval acknowledges terminal unseen state.
13. no duplicate benchmark polling loop is created.

## Chat

14. stream start → running.
15. stream success → short success → idle.
16. stream failure → failed.
17. opening Chat acknowledges failure according to policy.

## Files

18. one/multiple active file operations aggregate to running.
19. success transitions correctly.
20. failure transitions correctly.
21. displayed count is bounded and correct when available.

## UI/accessibility

22. running nav has accessible status text.
23. success/warning/failure do not rely on color only.
24. `prefers-reduced-motion` disables nonessential animation.
25. keyboard focus remains visible.
26. nav width/layout does not shift as activity changes.

Run focused Vitest.

Because this touches the application shell/top-level navigation:

```text
npm run build
```

is required.

---

# PART 15 — Manual visual acceptance

Capture screenshots / short screen recording for:

1. Eval running while Chat page is selected.
2. Eval success transition.
3. Eval failed/warning state.
4. Chat generating.
5. Files processing multiple files.
6. reduced-motion mode.

Check both:

```text
selected nav item
inactive nav item with background activity
```

The result should feel subtle, not game-like.

---

# Out of scope

Do not:

- change benchmark backend semantics;
- create fake ETA;
- change Chat generation logic;
- redesign the Eval page in this task (FRONT-04A owns that);
- create OS/browser notifications;
- add sound;
- add rapid blinking text;
- add permanent animated success/error states.

---

# Acceptance criteria

```text
[ ] Eval/Chat/Files share one bounded activity-state model.
[ ] Eval remains active in nav after navigating away.
[ ] Running uses a subtle accent animation, not blinking text.
[ ] Success uses a one-time green micro-animation.
[ ] Warning and failure are visually distinct.
[ ] Eval/Files terminal state can remain unseen until visited.
[ ] Chat success auto-clears.
[ ] Reduced-motion users get static status.
[ ] Color is never the only status cue.
[ ] No unnecessary idle polling is introduced.
[ ] Focused Vitest passes.
[ ] npm run build passes.
[ ] Manual visual checks look coherent with existing nav.
```

---

# Final report

Return exactly:

1. Shared activity architecture.
2. State mappings for Eval, Chat and Files.
3. Changed files grouped by:
   - app shell/nav
   - shared activity state
   - Eval integration
   - Chat integration
   - Files integration
   - tests/styles
4. Polling/network impact.
5. Animation behavior by state.
6. Reduced-motion behavior.
7. Acknowledgement policy.
8. Focused Vitest counts.
9. `npm run build` result.
10. Manual visual checks still required.
11. Known limitations/deferred work.

Do not commit or push.
