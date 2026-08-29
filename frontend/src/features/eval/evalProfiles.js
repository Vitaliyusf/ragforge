/**
 * Benchmark vocabulary for the Eval workspace: profiles, phase names and
 * the status tokens every surface renders from.
 *
 * The ids, phase lists and cost levels are the backend's own — this module
 * names them for the UI and adds nothing to their meaning. No profile is
 * given an ETA here, because nothing measures one.
 */

import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleDashed,
  Clock,
  Loader2,
  MinusCircle,
  PauseCircle,
  XCircle,
} from 'lucide-react'
import { EMPTY, formatScore } from '@/features/metrics/components/metricsConfig'

// One dash, one score format, for the whole app. The eval surfaces used to
// carry their own copies of both, which is how the same MRR came to be
// printed to two different precisions on one page.
export { EMPTY }

export const PHASE_LABELS = {
  retrieval_base: 'Retrieval baseline',
  retrieval_extended: 'Extended retrieval',
  end_to_end_regular: 'End-to-end',
  end_to_end_extended: 'Extended end-to-end',
}

/** Stepper-sized names. The full labels above do not fit a phase chip. */
export const PHASE_SHORT_LABELS = {
  retrieval_base: 'Retrieval',
  retrieval_extended: 'Extended retrieval',
  end_to_end_regular: 'Regular E2E',
  end_to_end_extended: 'Extended E2E',
}

/**
 * The five profiles, in ascending cost.
 *
 * `cost` is the qualitative level the profile has always carried. It is a
 * level, not a price: nothing here is described as free, and the two
 * profiles that run extended end-to-end phases say so before they start.
 */
export const PROFILES = [
  { id: 'quick_retrieval', label: 'Quick Retrieval', phases: ['retrieval_base'], cost: 'Fast' },
  { id: 'smoke_quality', label: 'Smoke Quality', phases: ['end_to_end_regular'], cost: 'Moderate' },
  {
    id: 'full_quality',
    label: 'Full Quality',
    phases: ['retrieval_base', 'end_to_end_regular'],
    cost: 'Moderate',
  },
  {
    id: 'extended_comparison',
    label: 'Extended Comparison',
    phases: ['end_to_end_regular', 'end_to_end_extended'],
    cost: 'Expensive',
  },
  {
    id: 'full_diagnostic',
    label: 'Full Diagnostic',
    phases: ['retrieval_base', 'end_to_end_regular', 'end_to_end_extended'],
    cost: 'Expensive',
  },
]

export const PROFILES_BY_ID = Object.fromEntries(PROFILES.map((profile) => [profile.id, profile]))

export const DEFAULT_PROFILE_ID = 'full_quality'

/** Cost levels map onto the shared badge tokens, never onto new colours. */
export const COST_VARIANTS = { Fast: 'default', Moderate: 'info', Expensive: 'warning' }

export function isExpensive(profile) {
  return profile?.cost === 'Expensive'
}

/** Said before an expensive profile starts, and again in its confirmation. */
export const EXPENSIVE_PROFILE_NOTE =
  'Expensive: runs Regular and Extended E2E over the selected dataset.'

export const PROFILE_HELP =
  'Runs a repeatable diagnostic workflow: every phase of the profile, in its safe order.'

export const SINGLE_EVAL_HELP =
  'Runs one retrieval or end-to-end eval without the benchmark workflow.'

/** The phases of a profile, as one compact line. */
export function profilePhaseSummary(profile) {
  return (profile?.phases || []).map((phase) => PHASE_SHORT_LABELS[phase] || phase).join(' · ')
}

/** The phases of a profile in full, for a confirmation dialog. */
export function profilePhaseNames(profile) {
  return (profile?.phases || []).map((phase) => PHASE_LABELS[phase] || phase).join(' + ')
}

/** Statuses a benchmark can no longer leave, and can be exported from. */
export const TERMINAL_STATUSES = new Set(['completed', 'partial', 'failed', 'interrupted'])

export function isTerminal(benchmark) {
  return TERMINAL_STATUSES.has(benchmark?.status)
}

export function isBenchmarkActive(benchmark) {
  return Boolean(benchmark?.benchmark_id) && !TERMINAL_STATUSES.has(benchmark.status)
}

/**
 * Run status, as a badge token plus an icon and a word.
 *
 * Every state carries text and an icon as well as a colour: the status must
 * still read on a monochrome display, or to a reader who cannot tell amber
 * from red.
 */
export const RUN_STATUS_META = {
  queued: { label: 'Queued', variant: 'default', icon: Clock },
  running: { label: 'Running', variant: 'accent', icon: Loader2, spin: true },
  completed: { label: 'Completed', variant: 'success', icon: CheckCircle2 },
  partial: { label: 'Partial', variant: 'warning', icon: AlertTriangle },
  interrupted: { label: 'Interrupted', variant: 'warning', icon: PauseCircle },
  failed: { label: 'Failed', variant: 'danger', icon: XCircle },
}

/**
 * Phase status.
 *
 * `unsupported` is deliberately muted rather than red: a phase this
 * deployment cannot execute did not fail, and colouring it as a failure
 * would report a broken benchmark where none ran.
 */
export const PHASE_STATUS_META = {
  completed: { label: 'Completed', variant: 'success', icon: CheckCircle2 },
  running: { label: 'Running', variant: 'accent', icon: Loader2, spin: true },
  queued: { label: 'Queued', variant: 'default', icon: CircleDashed },
  partial: { label: 'Partial', variant: 'warning', icon: AlertTriangle },
  failed: { label: 'Failed', variant: 'danger', icon: XCircle },
  interrupted: { label: 'Interrupted', variant: 'warning', icon: PauseCircle },
  unsupported: { label: 'Not supported', variant: 'default', icon: Ban },
  skipped: { label: 'Skipped', variant: 'default', icon: MinusCircle },
}

function humanize(value) {
  if (!value) return 'Unknown'
  const text = String(value).replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Never undefined: an unknown status still renders as its own word. */
export function statusMeta(status) {
  return (
    RUN_STATUS_META[status] || { label: humanize(status), variant: 'default', icon: CircleDashed }
  )
}

export function phaseStatusMeta(status) {
  return (
    PHASE_STATUS_META[status] || { label: humanize(status), variant: 'default', icon: CircleDashed }
  )
}

/** What a terminal run means, in words, beside its colour. */
export const TERMINAL_NOTES = {
  completed: 'Every executable phase finished. The archive holds the per-phase evidence.',
  partial: 'Some phases did not finish. The results below cover only the phases that did.',
  interrupted:
    'The run stopped before finishing. Progress up to that point is saved on the server.',
  failed: 'The run stopped after an error. Phases that completed before it are still exportable.',
}

// ---------------------------------------------------------------------------
// Time and number formatting
// ---------------------------------------------------------------------------

/** Seconds since a timestamp, or null when there is no usable timestamp. */
export function ageSeconds(value) {
  const timestamp = Date.parse(value || '')
  return Number.isFinite(timestamp)
    ? Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
    : null
}

export function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return EMPTY
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`
}

export function formatElapsed(value) {
  const seconds = ageSeconds(value)
  return seconds === null ? null : formatAge(seconds)
}

/**
 * How long a run took, from its own two timestamps.
 *
 * A run with no start time reports nothing rather than a duration measured
 * from a substitute timestamp that means something else. A run that started
 * and has not finished reports how long it has been going, which is what
 * the column is for while it is still going.
 */
export function formatDuration(startedAt, finishedAt) {
  const start = Date.parse(startedAt || '')
  const end = Date.parse(finishedAt || '')
  if (!Number.isFinite(start)) return EMPTY
  if (!Number.isFinite(end)) return formatAge(ageSeconds(startedAt))
  return formatAge(Math.max(0, Math.floor((end - start) / 1000)))
}

export function formatRunTimestamp(value) {
  const timestamp = Date.parse(value || '')
  return Number.isFinite(timestamp)
    ? new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }).format(timestamp)
    : EMPTY
}

/** Phases that produced numbers — the only ones with results to show. */
export function measuredPhases(benchmark) {
  return (benchmark?.phases || []).filter((phase) =>
    ['completed', 'partial'].includes(phase.status)
  )
}

/**
 * The one number that summarises a run in a history row.
 *
 * The last measured phase wins: a Full Quality run's end-to-end phase is
 * what its user came for, not the retrieval baseline that preceded it.
 */
export function keyResult(benchmark) {
  const measured = measuredPhases(benchmark)
  for (let index = measured.length - 1; index >= 0; index -= 1) {
    const mrr = measured[index]?.results?.mrr
    if (Number.isFinite(mrr)) return `MRR ${formatScore(mrr)}`
  }
  return EMPTY
}

/** No item has completed for this long, so the run may be wedged. */
export const STALL_SECONDS = 120
