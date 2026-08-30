/**
 * The status taxonomy.
 *
 * `statusTone` says how a status *looks*. This says what statuses *exist*,
 * and — more importantly — keeps five unrelated vocabularies from bleeding
 * into each other. A document is never "Healthy", a service is never
 * "Queued", and a connection is never "Passed".
 *
 * Every state resolves to a canonical label plus a tone, so a feature maps
 * its own backend vocabulary in once and never spells a status by hand.
 */

import { STATUS_TONES } from './statusTone'

export const STATUS_DOMAINS = Object.freeze({
  /** A thing the user owns: a document, an index, a golden set. */
  RESOURCE: 'resource',
  /** A deployable dependency reporting its own health. */
  SERVICE: 'service',
  /** One run of some work: a benchmark, an answer, an ingest. */
  EXECUTION: 'execution',
  /** A transport link — the browser's network, a stream, a socket. */
  CONNECTIVITY: 'connectivity',
  /** A human or judge verdict on content. */
  REVIEW: 'review',
})

const { NEUTRAL, INFO, LIVE, SUCCESS, WARNING, DANGER } = STATUS_TONES

/**
 * domain → state → { label, tone }.
 *
 * The state keys are the canonical spelling; anything a backend actually
 * emits reaches them through DOMAIN_ALIASES below.
 */
const DOMAIN_STATES = Object.freeze({
  [STATUS_DOMAINS.RESOURCE]: {
    ready: { label: 'Ready', tone: SUCCESS },
    processing: { label: 'Processing', tone: LIVE },
    failed: { label: 'Failed', tone: DANGER },
  },
  [STATUS_DOMAINS.SERVICE]: {
    healthy: { label: 'Healthy', tone: SUCCESS },
    degraded: { label: 'Degraded', tone: WARNING },
    unhealthy: { label: 'Unhealthy', tone: DANGER },
  },
  [STATUS_DOMAINS.EXECUTION]: {
    queued: { label: 'Queued', tone: INFO },
    running: { label: 'Running', tone: LIVE },
    completed: { label: 'Completed', tone: SUCCESS },
    // A run that finished without producing everything it was asked for is
    // not a success, and a green mark would claim otherwise.
    partial: { label: 'Partial', tone: WARNING },
    failed: { label: 'Failed', tone: DANGER },
    skipped: { label: 'Skipped', tone: NEUTRAL },
  },
  [STATUS_DOMAINS.CONNECTIVITY]: {
    connected: { label: 'Connected', tone: SUCCESS },
    disconnected: { label: 'Disconnected', tone: DANGER },
  },
  [STATUS_DOMAINS.REVIEW]: {
    passed: { label: 'Passed', tone: SUCCESS },
    needs_review: { label: 'Needs review', tone: WARNING },
    failed: { label: 'Failed', tone: DANGER },
  },
})

/**
 * Backend spellings that map onto a canonical state.
 *
 * Aliases are per-domain on purpose: `failed` means the same thing
 * everywhere, but `pending` is a queued execution and `error` is a failed
 * resource, and a single flat table would let one domain answer for another.
 */
const DOMAIN_ALIASES = Object.freeze({
  [STATUS_DOMAINS.RESOURCE]: {
    completed: 'ready',
    indexed: 'ready',
    processed: 'ready',
    pending: 'processing',
    uploading: 'processing',
    error: 'failed',
    rejected: 'failed',
  },
  [STATUS_DOMAINS.SERVICE]: {
    up: 'healthy',
    ok: 'healthy',
    down: 'unhealthy',
    error: 'unhealthy',
  },
  [STATUS_DOMAINS.EXECUTION]: {
    pending: 'queued',
    in_progress: 'running',
    success: 'completed',
    interrupted: 'partial',
    error: 'failed',
  },
  [STATUS_DOMAINS.CONNECTIVITY]: {
    online: 'connected',
    live: 'connected',
    offline: 'disconnected',
  },
  [STATUS_DOMAINS.REVIEW]: {
    approved: 'passed',
    pass: 'passed',
    review: 'needs_review',
    'needs-review': 'needs_review',
    pending: 'needs_review',
    rejected: 'failed',
  },
})

/** What a domain shows when the backend has told us nothing yet. */
const UNKNOWN = Object.freeze({ state: 'unknown', label: 'Unknown', tone: NEUTRAL })

function normalizeStateKey(state) {
  return String(state ?? '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_')
}

/**
 * Resolve a raw state within one domain.
 *
 * Unmeasured is `Unknown`, never an invented healthy/ready value — the same
 * rule the metrics surfaces follow for missing numbers.
 *
 * @param {string} domain one of STATUS_DOMAINS
 * @param {string} state the raw state a backend reported
 * @returns {{domain: string, state: string, label: string, tone: string, known: boolean}}
 */
export function describeStatus(domain, state) {
  const states = DOMAIN_STATES[domain]
  if (!states) throw new Error(`Unknown status domain: ${domain}`)
  const key = normalizeStateKey(state)
  const canonical = states[key] ? key : DOMAIN_ALIASES[domain]?.[key]
  const entry = canonical ? states[canonical] : null
  if (!entry) return { domain, ...UNKNOWN, known: false }
  return { domain, state: canonical, label: entry.label, tone: entry.tone, known: true }
}

/** The canonical states of a domain, in presentation order. */
export function statesOf(domain) {
  return Object.keys(DOMAIN_STATES[domain] || {})
}
