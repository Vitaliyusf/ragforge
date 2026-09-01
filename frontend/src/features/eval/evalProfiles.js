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
import { DEFAULT_LOCALE } from '@/i18n/locale'
import { translate } from '@/i18n/translate'

/**
 * English resolution for callers with no locale.
 *
 * The profile ids, phase ids and status values below are the benchmark
 * API's own and never change with the interface language; only the words
 * beside them do. Every table therefore carries a `labelKey`, and the
 * components resolve it at render time.
 */
const defaultTranslate = (key, variables) => translate(DEFAULT_LOCALE, key, variables)

// One dash, one score format, for the whole app. The eval surfaces used to
// carry their own copies of both, which is how the same MRR came to be
// printed to two different precisions on one page.
export { EMPTY }

export const PHASE_LABEL_KEYS = {
  retrieval_base: 'evalProfile.phase.retrievalBase',
  retrieval_extended: 'evalProfile.phase.retrievalExtended',
  end_to_end_regular: 'evalProfile.phase.endToEnd',
  end_to_end_extended: 'evalProfile.phase.endToEndExtended',
}

/** Stepper-sized names. The full labels above do not fit a phase chip. */
export const PHASE_SHORT_LABEL_KEYS = {
  retrieval_base: 'evalProfile.phaseShort.retrievalBase',
  retrieval_extended: 'evalProfile.phaseShort.retrievalExtended',
  end_to_end_regular: 'evalProfile.phaseShort.endToEnd',
  end_to_end_extended: 'evalProfile.phaseShort.endToEndExtended',
}

/**
 * The five profiles, in ascending cost.
 *
 * `cost` is the qualitative level the profile has always carried. It is a
 * level, not a price: nothing here is described as free, and the two
 * profiles that run extended end-to-end phases say so before they start.
 */
export const PROFILES = [
  {
    id: 'quick_retrieval',
    labelKey: 'evalProfile.quickRetrieval',
    phases: ['retrieval_base'],
    cost: 'Fast',
    costKey: 'evalProfile.cost.fast',
  },
  {
    id: 'smoke_quality',
    labelKey: 'evalProfile.smokeQuality',
    phases: ['end_to_end_regular'],
    cost: 'Moderate',
    costKey: 'evalProfile.cost.moderate',
  },
  {
    id: 'full_quality',
    labelKey: 'evalProfile.fullQuality',
    phases: ['retrieval_base', 'end_to_end_regular'],
    cost: 'Moderate',
    costKey: 'evalProfile.cost.moderate',
  },
  {
    id: 'extended_comparison',
    labelKey: 'evalProfile.extendedComparison',
    phases: ['end_to_end_regular', 'end_to_end_extended'],
    cost: 'Expensive',
    costKey: 'evalProfile.cost.expensive',
  },
  {
    id: 'full_diagnostic',
    labelKey: 'evalProfile.fullDiagnostic',
    phases: ['retrieval_base', 'end_to_end_regular', 'end_to_end_extended'],
    cost: 'Expensive',
    costKey: 'evalProfile.cost.expensive',
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
export const EXPENSIVE_PROFILE_NOTE_KEY = 'evalProfile.expensiveNote'

export const PROFILE_HELP_KEY = 'evalProfile.help'

export const SINGLE_EVAL_HELP_KEY = 'evalProfile.singleHelp'

/** The phases of a profile, as one compact line. */
export function profilePhaseSummary(profile, t = defaultTranslate) {
  return (profile?.phases || [])
    .map((phase) => (PHASE_SHORT_LABEL_KEYS[phase] ? t(PHASE_SHORT_LABEL_KEYS[phase]) : phase))
    .join(' · ')
}

/** The phases of a profile in full, for a confirmation dialog. */
export function profilePhaseNames(profile, t = defaultTranslate) {
  return (profile?.phases || [])
    .map((phase) => (PHASE_LABEL_KEYS[phase] ? t(PHASE_LABEL_KEYS[phase]) : phase))
    .join(' + ')
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
  queued: { labelKey: 'evalStatus.queued', variant: 'default', icon: Clock },
  running: { labelKey: 'evalStatus.running', variant: 'accent', icon: Loader2, spin: true },
  completed: { labelKey: 'evalStatus.completed', variant: 'success', icon: CheckCircle2 },
  partial: { labelKey: 'evalStatus.partial', variant: 'warning', icon: AlertTriangle },
  interrupted: { labelKey: 'evalStatus.interrupted', variant: 'warning', icon: PauseCircle },
  failed: { labelKey: 'evalStatus.failed', variant: 'danger', icon: XCircle },
}

/**
 * Phase status.
 *
 * `unsupported` is deliberately muted rather than red: a phase this
 * deployment cannot execute did not fail, and colouring it as a failure
 * would report a broken benchmark where none ran.
 */
export const PHASE_STATUS_META = {
  completed: { labelKey: 'evalStatus.completed', variant: 'success', icon: CheckCircle2 },
  running: { labelKey: 'evalStatus.running', variant: 'accent', icon: Loader2, spin: true },
  queued: { labelKey: 'evalStatus.queued', variant: 'default', icon: CircleDashed },
  partial: { labelKey: 'evalStatus.partial', variant: 'warning', icon: AlertTriangle },
  failed: { labelKey: 'evalStatus.failed', variant: 'danger', icon: XCircle },
  interrupted: { labelKey: 'evalStatus.interrupted', variant: 'warning', icon: PauseCircle },
  unsupported: { labelKey: 'evalStatus.unsupported', variant: 'default', icon: Ban },
  skipped: { labelKey: 'evalStatus.skipped', variant: 'default', icon: MinusCircle },
}

function humanize(value) {
  if (!value) return 'Unknown'
  const text = String(value).replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/**
 * Never undefined: an unknown status still renders as its own word.
 *
 * A status the backend adds but this build has no wording for falls back to
 * the humanised raw value — untranslated, because guessing a Hebrew name for
 * an unknown state would be inventing one.
 */
export function statusMeta(status, t = defaultTranslate) {
  const entry = RUN_STATUS_META[status]
  if (!entry) return { label: humanize(status), variant: 'default', icon: CircleDashed }
  return { ...entry, label: t(entry.labelKey) }
}

export function phaseStatusMeta(status, t = defaultTranslate) {
  const entry = PHASE_STATUS_META[status]
  if (!entry) return { label: humanize(status), variant: 'default', icon: CircleDashed }
  return { ...entry, label: t(entry.labelKey) }
}

/** What a terminal run means, in words, beside its colour. */
export const TERMINAL_NOTE_KEYS = {
  completed: 'evalStatus.note.completed',
  partial: 'evalStatus.note.partial',
  interrupted: 'evalStatus.note.interrupted',
  failed: 'evalStatus.note.failed',
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
