# REACT-19-01 — React 19 runtime architecture and compiler optimization

**Branch:** `perf/react19-runtime-architecture`  
**Phase:** Frontend / Product Track  
**Priority:** P1  
**Depends on:** `TAILWIND-04`

## Goal

Use React 19.2 to simplify the RagForge client runtime and reduce unnecessary rendering/effect complexity with measurable evidence.

This task combines the former `REACT-PERF-01` and `REACT-STATE-01` concepts because they inspect the same hotspots and would otherwise duplicate work.

This is **not** a product redesign.

## Target outcomes

```text
fewer unnecessary renders
fewer unnecessary Effects
fewer subscription reconnects
less stale-closure plumbing
less redundant manual memoization
smaller/clearer client boundaries
same behavior
```

Adopt a React 19 capability only when it removes real complexity or produces measurable value.

## Non-goals

- No Next.js navigation/cache redesign.
- No broad `<Activity>` rollout.
- No Chat redesign.
- No Files redesign.
- No Eval redesign.
- No Observability redesign.
- No new state-management framework.
- No frontend-wide dead-code scan.
- No Tailwind migration work.
- No mass formatting.

## Worktree safety

Before editing:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git worktree list
```

Expected branch:

`perf/react19-runtime-architecture`

Rules:

- Current source wins.
- Preserve unrelated dirty files.
- Never reset/stash/revert/clean.
- Prefer an isolated frontend worktree.
- No backend edits.
- No commit/push unless explicitly requested.
- Do not use `git add .` in a shared dirty worktree.

## Bounded inventory

Perform one React-specific inventory only. Do not repeat the TAILWIND-04 frontend-wide audit.

Measure:

- `'use client'` count
- `useEffect` count
- `useMemo` count
- `useCallback` count
- `React.memo` count
- client JS bytes/files
- available render/profiler evidence
- production build evidence

Prioritize:

```text
ChatContext
MessageList
FilesTab
EvalResults
PipelinePanel
Metrics surfaces
Header
WebSocket/subscription hooks
Logs hooks
Health/activity providers
```

Classify candidate modules:

```text
HOTSPOT
LOW_VALUE
PRODUCT_OWNED_DEFER
```

Store evidence under:

`.agent-private/tooling/REACT-19-01/`

## Phase A — React Compiler

Evaluate React Compiler using the supported React/Next integration available in the current source.

Do not assume it is beneficial because it is new.

Use comparable scenarios before/after where practical.

Capture:

- render count
- commit count
- unnecessary child renders
- interaction latency if reliable
- client JS impact
- build impact

Decision gate:

```text
measurable value or meaningful simplification
→ KEEP

no meaningful value / instability / unacceptable cost
→ REVERT and document
```

Do not combine the first compiler experiment with broad Effect rewrites; establish compiler impact first.

## Phase B — Manual memoization

Audit touched instances of:

- `React.memo`
- `useMemo`
- `useCallback`

Classify:

```text
REDUNDANT_RENDER_OPTIMIZATION
SEMANTIC_STABILITY_REQUIRED
EXPENSIVE_COMPUTATION_CACHE
EXTERNAL_API_IDENTITY
DEFER
```

Remove only behavior-equivalent redundancy.

Do not remove memoization required for:

- subscriptions
- third-party APIs
- stable imperative registration
- genuinely expensive computation

## Phase C — Effect architecture

Classify Effects in touched hotspots:

```text
EXTERNAL_SYNC
SUBSCRIPTION
TIMER
BROWSER_API
EVENT_LOGIC
DERIVED_STATE
EVENT_HANDLER_IN_DISGUISE
DUPLICATE_SYNC
DEAD
```

Rules:

- External synchronization normally remains an Effect.
- Derived state should usually be derived during render.
- Event-handler-in-disguise logic should move to the event path.
- Duplicate synchronization should be consolidated.
- Dead Effects should be removed with evidence.

Do not hide Effects inside new custom hooks merely to reduce a count.

## Phase D — `useEffectEvent`

Use `useEffectEvent` where an Effect needs a stable lifecycle/subscription while callbacks need the latest non-reactive state.

Strong candidates:

```text
WebSocket callbacks
Socket.IO subscriptions
logs streams
metrics subscriptions
visibility/activity listeners
theme-aware callbacks that must not reconnect
```

Target:

```text
stable subscription lifecycle
+
latest callback/state through Effect Event
```

Measure where practical:

- reconnect/resubscribe count
- duplicate-subscription risk
- dependency-array complexity

Do not use `useEffectEvent` as a generic callback replacement.

## Phase E — Derived state

Audit touched `useState + useEffect` patterns.

Remove duplicated state when it can be derived directly from current props/query/context.

Preserve intentionally staged/draft state.

## Phase F — Client boundaries

After runtime cleanup, reassess touched `'use client'` files.

Remove `'use client'` only when the component no longer requires:

- hooks
- event handlers
- browser APIs
- client-only context
- client-only third-party libraries

Do not force Server Component conversion.

## `<Activity>` ownership

Do **not** broadly adopt `<Activity>` here.

Its value depends on navigation, state persistence and mount/unmount behavior, so broad adoption belongs to `NEXT-16-01`.

## `useOptimistic`

Do not build a generic optimistic framework here.

Feature-owned optimistic UX belongs to:

```text
CHAT-01
FILES-LIST-01
Admin/product mutation flows
```

## Regression tests

Add application behavior tests only where runtime behavior changes, for example:

- subscription registers once
- cleanup/unsubscribe occurs once
- callback sees latest state without reconnect
- derived state remains correct
- duplicate events are not emitted

Do not test hook implementation trivia.

## Performance evidence

Capture before/after where reliable:

```text
render/commit evidence
'use client'
useEffect
useMemo
useCallback
React.memo
client JS bytes/files
build result
```

Do not claim an improvement from one noisy run.

If profiler infrastructure is unavailable, state the limitation and use structural evidence plus deterministic tests.

## Performance budget

No unexplained regression:

```text
client JS >5%
CSS >10%
new runtime dependency >0 without justification
'use client' increase without reason
useEffect increase during modernization
```

Build duration is informational because cache state is noisy.

## Validation

Use:

> TEST WHAT CHANGED. LET CI TEST THE REPOSITORY.

During iteration:

```text
smallest focused tests
```

Near completion:

```text
focused hotspot tests
→ affected feature tests
→ full frontend suite once
→ Next production build
→ configured static/type checks if any
→ git diff --check
```

No backend tests.

## Stop/defer rules

```text
navigation/persistent shell     → NEXT-16-01
Chat architecture/UX           → CHAT-01
Files listing/mutations        → FILES-LIST-01
Eval decomposition             → EVAL-UX-01
Metrics/Logs/Health workflows  → OBS-UX-01
final motion/a11y polish       → FRONT-POLISH-01
```

Do not broaden scope to remove every Effect in the repository.

## Completion report

Report:

```text
REACT-19-01

branch:

compiler:
  before:
  after:
  decision:
  evidence:

runtime counts:
  use client before/after:
  useEffect before/after:
  useMemo before/after:
  useCallback before/after:
  React.memo before/after:

effects:
  external sync retained:
  derived state removed:
  event-handler effects removed:
  duplicate subscriptions removed:
  useEffectEvent adoptions:

client boundaries:
  removed:
  retained with reason:

performance:
  render evidence:
  client JS before/after:
  build evidence:
  limitations:

validation:
  focused:
  affected:
  full frontend:
  build:
  static/type:
  diff check:

deferred intentionally:

resume/interview evidence:

final status:
```

## Closeout

After all source edits and validation:

```text
NO MORE SOURCE EDITS
→ record one REACT-19-01 handoff
→ update frontend metrics evidence
→ rebuild repo brain once
→ validate repo brain once
→ STOP
```

Do not start `NEXT-16-01`.
