# CHAT-01 — Chat product experience and Developer Inspector

**Branch:** `feat/chat-product-experience`  
**Phase:** Frontend / Product Track  
**Depends on:** `FRONT-FOUNDATION-01`

## Goal

Make Chat clean for a knowledge user while preserving deep engineering inspection through an explicit Developer Inspector.

## Default user experience

The default answer surface should prioritize:

```text
answer
sources
feedback
compact quality state
```

Do not show by default:
- raw review UUID
- zero UUID placeholders
- raw epoch timestamps
- full internal model slug
- raw evaluator payload
- full prompt
- trace internals

Format timestamps for humans.

## Compact answer quality

Prefer a compact summary such as:

```text
Grounded · 3 sources · Review passed
```

For abstention/no-answer cases, represent answerability explicitly rather than misleading percentages.

Example:
```text
Answerability: No supporting evidence
Decision: Correctly abstained
```

## Developer Inspector

Provide an explicit drawer/panel with sections such as:

```text
Overview
Retrieval
Context
Generation
Quality
Trace
```

Only show fields actually backed by data.

Potential content:
- retrieved chunks
- retrieval/reranker scores
- source metadata
- generation model/runtime
- token counts
- TTFT/latency
- quality verdict
- prompt
- trace/correlation identifiers

Sensitive content should be redacted by default where appropriate.

## Conversation behavior

Fix/verify:
- conversation appears in Recent Chats after first persisted turn
- auto title after first useful user turn
- rename/delete behavior remains correct
- long conversation remains responsive

## RTL / Bidi

Message content should use direction-aware behavior (`dir=auto` or equivalent).

Technical strings such as:
- model IDs
- code
- UUIDs
- trace IDs

remain LTR.

Validate mixed Hebrew/English punctuation and metadata layout.

## Activity states

Remove duplicated vague `Live` indicators from Chat.

If backend exposes real stages, show stage-aware state:
- Retrieving sources…
- Reranking…
- Generating answer…
- Reviewing…

Never fake progress.

If only generic request state exists, show generic real state.

## Motion

Keep idle UI calm.

Use subtle state transitions only for:
- new streamed content
- inspector open/close
- real execution stage updates
- conversation list insertion/deletion

Respect reduced motion.

## Refactor touched scope

While implementing:
- split oversized Chat components
- move API/data logic into appropriate hooks/services
- remove dead Chat-specific styles/components
- remove duplicated answer metadata formatting
- avoid duplicated state/effects

No unrelated frontend cleanup.

## Performance acceptance

Validate a representative long thread (~200 messages or synthetic equivalent):
- no obvious input lag
- no pathological rerender behavior
- scrolling remains usable

Use virtualization only if measurement justifies it.

## Tests

```text
chat focused tests
→ persistence/title tests
→ inspector visibility tests
→ RTL/bidi tests
→ long-thread performance sanity check
→ full frontend suite once
→ production build
→ git diff --check
```

STOP. Do not start FILES-LIST-01.
