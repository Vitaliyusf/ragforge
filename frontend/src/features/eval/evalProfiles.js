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

/**
 * A span of seconds as `Nm SSs` — the one duration format this feature uses.
 *
 * A negative span keeps its sign rather than being clamped to zero. A run
 * whose end precedes its start has contradictory timestamps, and `0m 00s`
 * would present that contradiction as a believable measurement.
 */
export function formatSpan(seconds) {
  const sign = seconds < 0 ? '-' : ''
  const total = Math.abs(seconds)
  return `${sign}${Math.floor(total / 60)}m ${String(total % 60).padStart(2, '0')}s`
}

export function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return EMPTY
  return formatSpan(seconds)
}

export function formatElapsed(value) {
  const seconds = ageSeconds(value)
  return seconds === null ? null : formatAge(seconds)
}

/**
 * The span between two run timestamps, or a truthful reason there is none.
 *
 * The single duration primitive every timing label on this feature is built
 * from. Three rules, and they are the reason the callers below exist as
 * separate named helpers rather than as three calls to this one:
 *
 * - No usable opening timestamp reports nothing. A duration measured from a
 *   substitute timestamp means something other than what its label claims,
 *   and that is precisely the bug this replaced.
 * - No usable closing timestamp measures to now. The span is still running,
 *   and how long it has been running is what the label is for.
 * - A closing timestamp that precedes the opening one is reported with its
 *   sign, never clamped. See {@link formatSpan}.
 */
export function durationBetween(fromValue, toValue, now = Date.now()) {
  const from = Date.parse(fromValue || '')
  if (!Number.isFinite(from)) return EMPTY
  const to = Date.parse(toValue || '')
  return formatSpan(Math.trunc(((Number.isFinite(to) ? to : now) - from) / 1000))
}

/**
 * How long a benchmark waited before its worker entered `running`.
 *
 * Grows against the clock while the run is still queued, which is the only
 * honest thing to show somebody watching a run that has not started.
 */
export function benchmarkQueueDuration(createdAt, startedAt, now) {
  return durationBetween(createdAt, startedAt, now)
}

/** How long the benchmark worker actually ran, queue time excluded. */
export function benchmarkExecutionDuration(startedAt, finishedAt, now) {
  return durationBetween(startedAt, finishedAt, now)
}

/**
 * How long the run took as its user experienced it.
 *
 * From creation, because that is when somebody pressed the button and began
 * waiting — not from the moment a worker got round to the job.
 */
export function benchmarkTotalDuration(createdAt, finishedAt, now) {
  return durationBetween(createdAt, finishedAt, now)
}

/**
 * The three spans of one benchmark, resolved against its status.
 *
 * The status is what decides whether an open span may be measured against
 * the clock, and no timestamp pair can answer that on its own. An active run
 * with no `finished_at` has not finished yet, so its total is still growing.
 * A **terminal** run with no `finished_at` is a different thing entirely: it
 * is a closed record whose end was never written, and measuring it against
 * `Date.now()` would show a completed benchmark whose duration climbs for
 * ever. That is incomplete evidence, and it reports a dash.
 *
 * The rule lives here rather than in {@link durationBetween} because the
 * primitive is also what measures genuinely open spans, and teaching it to
 * refuse the clock would break the live run it exists to serve.
 */
export function benchmarkSpans(run, now) {
  const created = run?.created_at
  const started = run?.started_at
  const finished = run?.finished_at
  if (TERMINAL_STATUSES.has(run?.status)) {
    // A closed record is measured only from what it actually recorded.
    return {
      queue: closedSpan(created, started),
      execution: closedSpan(started, finished),
      total: closedSpan(created, finished),
    }
  }
  return {
    queue: benchmarkQueueDuration(created, started, now),
    // A run that has not started has executed for no time anybody can
    // name, which is not the same as having executed for none.
    execution: benchmarkExecutionDuration(started, finished, now),
    total: benchmarkTotalDuration(created, finished, now),
  }
}

/** A span that reports nothing rather than measuring an absent end to now. */
function closedSpan(fromValue, toValue) {
  return Number.isFinite(Date.parse(toValue || ''))
    ? durationBetween(fromValue, toValue)
    : EMPTY
}

/**
 * How long a single evaluation run took.
 *
 * An evaluation has one pair of timestamps and no queue of its own, so
 * start-to-finish is unambiguous here in a way it is not for a benchmark.
 */
export function formatDuration(startedAt, finishedAt) {
  return durationBetween(startedAt, finishedAt)
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
