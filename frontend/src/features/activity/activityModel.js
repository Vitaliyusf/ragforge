/**
 * The one activity vocabulary the navigation understands.
 *
 * Eval, Chat and Files each have their own backend lifecycle. Rather than
 * teaching the header three of them, every feature maps its own truth into
 * the six states below, and the nav renders states — never feature-specific
 * status strings. Nothing here polls, fetches or remembers: it is pure
 * mapping, so it can be tested without a DOM.
 */

import { PRODUCT_LABELS } from '@/lib/terminology'

export const ACTIVITY_STATES = Object.freeze({
  IDLE: 'idle',
  QUEUED: 'queued',
  RUNNING: 'running',
  SUCCESS: 'success',
  WARNING: 'warning',
  FAILED: 'failed',
})

export const ACTIVITY_FEATURES = Object.freeze({
  EVAL: 'eval',
  CHAT: 'chat',
  FILES: 'files',
})

/** Nothing is happening. The nav renders its ordinary appearance. */
export const IDLE_ACTIVITY = Object.freeze({ state: ACTIVITY_STATES.IDLE })

const ACTIVE_STATES = new Set([ACTIVITY_STATES.QUEUED, ACTIVITY_STATES.RUNNING])
const TERMINAL_STATES = new Set([
  ACTIVITY_STATES.SUCCESS,
  ACTIVITY_STATES.WARNING,
  ACTIVITY_STATES.FAILED,
])

export function isActiveState(state) {
  return ACTIVE_STATES.has(state)
}

export function isTerminalState(state) {
  return TERMINAL_STATES.has(state)
}

/**
 * Text is bounded on purpose.
 *
 * Global activity state is read by the header on every render and may be
 * shown in a tooltip; it is not a place for prompts, document text or error
 * bodies. Anything longer than a short phrase is cut here rather than
 * trusted to whatever produced it.
 */
export const MAX_ACTIVITY_TEXT = 72

export function boundedText(value) {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim().replace(/\s+/g, ' ')
  if (!trimmed) return undefined
  return trimmed.length > MAX_ACTIVITY_TEXT
    ? `${trimmed.slice(0, MAX_ACTIVITY_TEXT - 1)}…`
    : trimmed
}

/** The only keys the nav will carry. Anything else a feature sends is dropped. */
const ENTRY_KEYS = ['state', 'label', 'startedAt', 'completedAt', 'progress', 'count', 'message']

/**
 * Normalize a feature's entry into the bounded shape the nav renders.
 *
 * Unknown states collapse to idle rather than rendering an indicator nobody
 * can explain, and progress is kept only when both halves are real numbers —
 * an invented denominator would read as a fake ETA.
 */
export function normalizeActivity(entry) {
  if (!entry || !Object.values(ACTIVITY_STATES).includes(entry.state)) return { ...IDLE_ACTIVITY }
  const normalized = { state: entry.state }
  for (const key of ENTRY_KEYS) {
    if (key === 'state') continue
    const value = entry[key]
    if (value === undefined || value === null) continue
    if (key === 'label' || key === 'message') {
      const text = boundedText(value)
      if (text) normalized[key] = text
    } else if (key === 'count') {
      if (Number.isFinite(value) && value > 0) normalized.count = Math.trunc(value)
    } else if (key === 'progress') {
      const completed = Number(value.completed)
      const total = Number(value.total)
      if (Number.isFinite(completed) && Number.isFinite(total) && total > 0) {
        normalized.progress = { completed, total }
      }
    } else {
      normalized[key] = value
    }
  }
  return normalized
}

/**
 * Acknowledgement clears a terminal state and nothing else.
 *
 * Visiting a feature while it is still working must not silence the
 * indicator — the work is still happening, and the nav is the only place
 * that says so once the user leaves again.
 */
export function acknowledgeActivity(entry) {
  return isTerminalState(entry?.state) ? { ...IDLE_ACTIVITY } : normalizeActivity(entry)
}

/* ── Eval ──────────────────────────────────────────────────────────────── */

/**
 * Benchmark status → activity state.
 *
 * `partial` and `interrupted` are warnings, not successes: a run that
 * skipped phases produced fewer measurements than it was asked for, and a
 * green nav dot would claim otherwise.
 */
export const BENCHMARK_ACTIVITY_STATES = Object.freeze({
  queued: ACTIVITY_STATES.QUEUED,
  pending: ACTIVITY_STATES.QUEUED,
  running: ACTIVITY_STATES.RUNNING,
  completed: ACTIVITY_STATES.SUCCESS,
  partial: ACTIVITY_STATES.WARNING,
  interrupted: ACTIVITY_STATES.WARNING,
  failed: ACTIVITY_STATES.FAILED,
})

export function mapBenchmarkStatus(status) {
  if (!status) return ACTIVITY_STATES.IDLE
  return BENCHMARK_ACTIVITY_STATES[String(status).toLowerCase()] || ACTIVITY_STATES.RUNNING
}

/* ── Chat ──────────────────────────────────────────────────────────────── */

export const CHAT_ACTIVITY_STATES = Object.freeze({
  idle: ACTIVITY_STATES.IDLE,
  connecting: ACTIVITY_STATES.RUNNING,
  streaming: ACTIVITY_STATES.RUNNING,
  done: ACTIVITY_STATES.SUCCESS,
  error: ACTIVITY_STATES.FAILED,
})

export function mapChatState(chatState) {
  return CHAT_ACTIVITY_STATES[chatState] ?? ACTIVITY_STATES.IDLE
}

/* ── Files ─────────────────────────────────────────────────────────────── */

export const FILE_ACTIVE_STATUSES = new Set(['processing'])
export const FILE_FAILED_STATUSES = new Set(['error', 'rejected'])

/* ── Accessible status text ────────────────────────────────────────────── */

const FEATURE_LABELS = {
  [ACTIVITY_FEATURES.EVAL]: PRODUCT_LABELS.eval,
  [ACTIVITY_FEATURES.CHAT]: PRODUCT_LABELS.chat,
  [ACTIVITY_FEATURES.FILES]: PRODUCT_LABELS.knowledge,
}

/**
 * One short sentence describing the state, for `aria-label` and the tooltip.
 *
 * The same string serves both: the tooltip must never be the only place the
 * status exists, or a keyboard or screen-reader user would have no way to
 * read it.
 */
export function describeActivity(feature, entry) {
  const activity = normalizeActivity(entry)
  const name = FEATURE_LABELS[feature] || feature
  if (activity.state === ACTIVITY_STATES.IDLE) return name

  const parts = [activity.message || DEFAULT_PHRASES[feature]?.[activity.state] || activity.state]
  if (activity.progress) parts.push(`${activity.progress.completed}/${activity.progress.total}`)
  if (activity.label) parts.push(activity.label)
  return `${name} — ${parts.join(' · ')}`
}

const DEFAULT_PHRASES = {
  [ACTIVITY_FEATURES.EVAL]: {
    queued: 'benchmark queued',
    running: 'benchmark running',
    success: 'benchmark completed',
    warning: 'benchmark finished partially',
    failed: 'benchmark failed',
  },
  [ACTIVITY_FEATURES.CHAT]: {
    queued: 'request queued',
    running: 'generating response',
    success: 'response ready',
    warning: 'response incomplete',
    failed: 'last request failed',
  },
  [ACTIVITY_FEATURES.FILES]: {
    queued: 'indexing queued',
    running: 'indexing documents',
    success: 'indexing finished',
    warning: 'needs review',
    failed: 'indexing failed',
  },
}
