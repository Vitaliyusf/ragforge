/**
 * The run report's data model.
 *
 * Every derivation the report renders happens here: which stages ran, what
 * the headline numbers are, what a failure means, and whether two runs may
 * be compared at all. The components below `components/report/` read this
 * shape and add no arithmetic of their own — a number that appears on the
 * page can always be traced to one function in this file.
 *
 * Formatting is part of the model rather than of the components: the same
 * measurement must read identically wherever it is shown, and three copies
 * of "how do we print an MRR" is exactly what this module replaced.
 */

import {
  EMPTY,
  EVAL_HISTORY_K,
  EVAL_METRIC_LABELS,
  EVAL_MODE_LABELS,
  FAILURE_CATEGORY_LABELS,
  formatCount,
  formatMs,
  formatPercent,
  formatScore,
  formatSetting,
  labelFor,
} from '@/features/metrics/components/metricsConfig'
import {
  PHASE_LABELS,
  PROFILES_BY_ID,
  formatDuration,
  formatRunTimestamp,
  isTerminal,
  statusMeta,
} from './evalProfiles'

/** The stage every run begins with, before any retrieval happens. */
export const VALIDATION_STAGE = 'dataset_validation'

const VALIDATION_LABEL = 'Dataset validation'

/** Stage states that stop everything after them from running. */
const BLOCKING_STATUSES = new Set(['failed', 'interrupted'])

/** Stage states that mean "this never started", not "this went wrong". */
const NOT_RUN_STATUSES = new Set(['queued', 'skipped'])

// ---------------------------------------------------------------------------
// Latency
// ---------------------------------------------------------------------------

/**
 * The value at a quantile of an already-sorted sample, or null.
 *
 * Nearest-rank, so every reported percentile is a latency some query
 * actually took rather than an interpolation between two that nobody did.
 */
export function percentile(sorted, quantile) {
  if (!sorted?.length) return null
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(quantile * sorted.length) - 1))
  return sorted[index]
}

/**
 * Latency percentiles over the per-item rows a run kept.
 *
 * `sample` is reported beside them because a p95 over nine items is not a
 * tail measurement. A run whose rows carry no latency reports nulls — the
 * mean the server computed is still shown, and nothing is invented here.
 */
export function latencySummary(rows) {
  const values = (rows || [])
    .map((row) => row?.latency_ms)
    .filter((value) => Number.isFinite(value))
    .sort((left, right) => left - right)
  return {
    p50: percentile(values, 0.5),
    p95: percentile(values, 0.95),
    sample: values.length,
  }
}

// ---------------------------------------------------------------------------
// Stages
// ---------------------------------------------------------------------------

/**
 * How the run's ground truth checked out, as the first stage of the flow.
 *
 * A run that never checked is `unknown`, never `completed`: the check is
 * what makes the scores mean anything, and reporting it as passed because
 * nothing objected is the one claim this stage must not make.
 */
export function validationStage(validation) {
  if (!validation) {
    return {
      key: VALIDATION_STAGE,
      label: VALIDATION_LABEL,
      status: 'unknown',
      note: 'This run recorded no label check.',
    }
  }
  if (!validation.checked) {
    return {
      key: VALIDATION_STAGE,
      label: VALIDATION_LABEL,
      status: 'unknown',
      note: 'The labels behind this run were never verified against the index.',
    }
  }
  const stale = (validation.stale_label_count || 0) + (validation.unretrievable_label_count || 0)
  return {
    key: VALIDATION_STAGE,
    label: VALIDATION_LABEL,
    status: stale ? 'partial' : 'completed',
    note: stale
      ? `${formatCount(stale)} labels are no longer in the index.`
      : 'Every label was found in the live index.',
  }
}

/**
 * The execution flow, in causal order, with the reason each stage is in the
 * state it is in.
 *
 * A stage that never ran because an earlier one failed says so and names
 * that stage. It is not marked failed, and it is not left looking like a
 * choice somebody made: skipped is not failed, and a reader who cannot tell
 * the two apart will go and debug the wrong thing.
 */
export function executionFlow(stages) {
  let blocker = null
  return (stages || []).map((stage) => {
    const next = { ...stage }
    if (blocker && NOT_RUN_STATUSES.has(stage.status)) {
      next.status = 'skipped'
      next.blockedBy = blocker.label
      next.note = `Not run: ${blocker.label} ${blocker.status === 'failed' ? 'failed' : 'stopped'} first.`
    }
    if (!blocker && BLOCKING_STATUSES.has(stage.status)) blocker = stage
    return next
  })
}

/** A benchmark's phases as flow stages, with the validation stage in front. */
function benchmarkStages(benchmark, validation) {
  const phases = (benchmark?.phases || []).map((phase) => ({
    key: phase.name,
    label: PHASE_LABELS[phase.name] || phase.name,
    status: phase.status,
    note: phase.reason || phase.error || null,
    results: phase.results || null,
  }))
  return executionFlow([validationStage(validation), ...phases])
}

// ---------------------------------------------------------------------------
// Measurements
// ---------------------------------------------------------------------------

/**
 * The measured phases of a run, newest-measured last.
 *
 * A phase with no results is not a measurement: it contributes no numbers,
 * and listing it would put an empty tab body on the page.
 */
function benchmarkMeasurements(benchmark) {
  return (benchmark?.phases || [])
    .filter((phase) => phase.results && ['completed', 'partial'].includes(phase.status))
    .map((phase) => ({
      key: phase.name,
      label: PHASE_LABELS[phase.name] || phase.name,
      status: phase.status,
      results: phase.results,
      items: [],
    }))
}

// ---------------------------------------------------------------------------
// KPI summary
// ---------------------------------------------------------------------------

/**
 * The headline figures, in the order an engineer reads them.
 *
 * Every card carries its denominator: a Recall@5 over three items and one
 * over three hundred are the same number and different evidence. An absent
 * measurement is a dash — never a zero, which is a result.
 */
export function kpiSummary(measurement) {
  if (!measurement?.results) return []
  const results = measurement.results
  const quality = results.answer_quality
  const latency = latencySummary(measurement.items)
  const scored = results.items_evaluated

  const cards = [
    {
      key: 'mrr',
      label: EVAL_METRIC_LABELS.mrr,
      value: formatScore(results.mrr),
      subLabel: `mean reciprocal rank over ${formatCount(scored)} scored items`,
    },
    {
      key: 'recall',
      label: `Recall@${EVAL_HISTORY_K}`,
      value: formatPercent(results.recall_at_k?.[EVAL_HISTORY_K]),
      subLabel: 'labelled chunks found in the top five',
    },
    {
      key: 'ndcg',
      label: EVAL_METRIC_LABELS.ndcg_at_10,
      value: formatScore(results.ndcg_at_k?.['10']),
      subLabel: 'rewards ranking hits high, not just finding them',
    },
    {
      key: 'latency',
      label: latency.p95 === null ? EVAL_METRIC_LABELS.mean_latency_ms : 'Latency p95',
      value: latency.p95 === null ? formatMs(results.mean_latency_ms) : formatMs(latency.p95),
      subLabel:
        latency.p95 === null
          ? 'per query — this run kept no per-item latencies to take a tail from'
          : `p50 ${formatMs(latency.p50)} over ${formatCount(latency.sample)} queries`,
    },
    {
      key: 'failures',
      label: 'Failed items',
      value: formatCount(results.items_failed),
      variant: results.items_failed > 0 ? 'danger' : 'default',
      subLabel: `${formatCount(results.items_skipped)} unlabelled, ${formatCount(
        results.items_unscorable
      )} unscorable`,
    },
  ]

  if (quality) {
    cards.push({
      key: 'groundedness',
      label: 'Groundedness',
      value: formatScore(quality.groundedness?.mean),
      subLabel: `${formatCount(quality.items_judged)} judged, ${formatCount(
        quality.items_unjudged
      )} unjudged`,
    })
  }
  return cards
}

// ---------------------------------------------------------------------------
// Failure explanation
// ---------------------------------------------------------------------------

const FAILURE_COPY = {
  failed: {
    title: 'The run stopped after an error',
    happened: 'The run stopped while executing, and no single stage recorded the error.',
    impact: 'Phases that had already finished are still measured; nothing after the error ran.',
  },
  interrupted: {
    title: 'The run was interrupted before it finished',
    happened: 'The run was stopped from outside rather than by an error of its own.',
    impact: 'Progress up to the interruption is saved. The remaining phases were never executed.',
  },
  partial: {
    title: 'Some phases did not finish',
    happened: 'At least one phase ended without producing a full set of results.',
    impact: 'The figures below cover only the phases that completed.',
  },
}

/**
 * Likely causes, matched on the error text the service actually writes.
 *
 * Only patterns whose evidence is in the message itself are here. A run
 * whose error matches nothing gets no cause at all rather than a plausible
 * guess: a wrong cause costs more debugging time than an absent one.
 */
const CAUSE_PATTERNS = [
  [/timed? ?out|timeout/i, 'A downstream call exceeded its deadline. The service was reachable but slow.'],
  [/unavailable|refused|connect|unreachable/i, 'A dependency the run needs was not reachable while it executed.'],
  [/unauthori[sz]ed|forbidden|permission|denied/i, 'The run was refused by a dependency on authorization, not on data.'],
  [/rate.?limit|quota|429/i, 'A provider rate limit or quota was reached during the run.'],
  [/no items|empty|has no/i, 'The dataset carried nothing this phase could score.'],
]

function likelyCause(error) {
  const text = String(error || '')
  const match = CAUSE_PATTERNS.find(([pattern]) => pattern.test(text))
  return match ? match[1] : null
}

/**
 * A failure in product language, with the raw text kept for the technical
 * section rather than used as the headline.
 *
 * `actions` names only what the report can actually do; a "view trace"
 * button that opens nothing is worse than no button, because it costs a
 * click and a rebuilt expectation before it teaches the same thing.
 */
export function explainFailure({ status, error, stages = [], retryable = false, exportable = false }) {
  const copy = FAILURE_COPY[status]
  if (!copy) return null
  const failedStage = stages.find((stage) => BLOCKING_STATUSES.has(stage.status))
  const blocked = stages.filter((stage) => stage.blockedBy)
  const actions = []
  if (retryable) actions.push('retry')
  if (exportable) actions.push('download')

  return {
    status,
    title: copy.title,
    happened: failedStage
      ? `${failedStage.label} ${failedStage.status === 'failed' ? 'failed' : 'stopped'} while the run was executing.`
      : copy.happened,
    impact: blocked.length
      ? `${copy.impact} ${blocked.map((stage) => stage.label).join(', ')} never ran.`
      : copy.impact,
    cause: likelyCause(error || failedStage?.note),
    actions,
    technical: error || failedStage?.note || null,
  }
}

// ---------------------------------------------------------------------------
// Comparison integrity
// ---------------------------------------------------------------------------

/**
 * Provenance a comparison depends on. Two runs that disagree on any of it
 * are measuring different things, however similar their numbers look.
 */
const PROVENANCE_GROUPS = {
  dataset: ['dataset_id', 'dataset_version', 'dataset_sha256'],
  config: ['manifest.dataset.phases', 'manifest.chunking', 'manifest.vector_store'],
  model: ['manifest.embedding', 'manifest.llm'],
  retrieval: ['manifest.retrieval'],
}

/** Human names for the provenance paths above, which are not snapshot keys. */
const PROVENANCE_LABELS = {
  dataset_id: 'Dataset',
  dataset_version: 'Dataset version',
  dataset_sha256: 'Dataset fingerprint',
  'manifest.dataset.phases': 'Phases',
  'manifest.chunking': 'Chunking',
  'manifest.vector_store': 'Vector store',
  'manifest.embedding': 'Embedding',
  'manifest.llm': 'LLM',
  'manifest.retrieval': 'Retrieval',
}

/**
 * A provenance value as text.
 *
 * These are whole manifest sections as often as they are scalars, so a
 * structured value is printed as compact JSON rather than as the string
 * `[object Object]`, which tells the reader nothing about what changed.
 */
export function formatProvenanceValue(value) {
  if (value === null || value === undefined || value === '') return EMPTY
  if (typeof value === 'object') return JSON.stringify(value)
  return formatSetting(value)
}

function atPath(value, path) {
  return path.split('.').reduce((current, key) => current?.[key], value)
}

function same(left, right) {
  return left != null && right != null && JSON.stringify(left) === JSON.stringify(right)
}

/**
 * Whether two benchmark runs may be compared, and on what they disagree.
 *
 * A field missing from either side is a `unknown` mismatch rather than a
 * match: two runs that both failed to record their embedding model have not
 * been shown to share one.
 */
export function compatibility(baseline, candidate) {
  const warnings = []
  Object.entries(PROVENANCE_GROUPS).forEach(([category, paths]) =>
    paths.forEach((field) => {
      const left = atPath(baseline, field)
      const right = atPath(candidate, field)
      if (!same(left, right)) {
        warnings.push({
          category,
          field,
          label: labelFor(PROVENANCE_LABELS, field),
          baseline: left,
          candidate: right,
          kind: left == null || right == null ? 'unknown' : 'mismatch',
        })
      }
    })
  )
  return { compatible: warnings.length === 0, warnings }
}

function priorRuns(candidate, history) {
  const candidateTime = Date.parse(candidate?.created_at || '')
  return (history || []).filter(
    (run) =>
      run.benchmark_id !== candidate?.benchmark_id &&
      ['completed', 'partial', 'failed', 'interrupted'].includes(run.status) &&
      (!Number.isFinite(candidateTime) ||
        !Number.isFinite(Date.parse(run.created_at || '')) ||
        Date.parse(run.created_at) < candidateTime)
  )
}

/** The most recent prior run, compatible or not — comparability is reported, not hidden. */
export function selectBaseline(candidate, history = []) {
  return priorRuns(candidate, history)[0] || null
}

/**
 * Which direction is an improvement, per metric family.
 *
 * A metric absent from this table gets an uncoloured delta: a number whose
 * good direction nobody has defined must not be painted green.
 */
export const METRIC_DIRECTION = { mrr: 'up', recall: 'up', ndcg: 'up', latency: 'down' }

function deltaOf(baseline, candidate) {
  if (!Number.isFinite(baseline) || !Number.isFinite(candidate)) {
    return { absolute: null, percentage: null }
  }
  const absolute = candidate - baseline
  return { absolute, percentage: baseline === 0 ? null : (absolute / Math.abs(baseline)) * 100 }
}

/** A signed delta, or a dash. Never a confident zero for an absent figure. */
export function formatDelta(value, digits = 2, suffix = '') {
  if (!Number.isFinite(value)) return EMPTY
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`
}

/**
 * How a delta should read: better, worse, or simply changed.
 *
 * `null` means the metric has no defined direction, and the report colours
 * nothing on it.
 */
export function deltaTone(metric, absolute) {
  const direction = METRIC_DIRECTION[metric]
  if (!direction || !Number.isFinite(absolute) || absolute === 0) return null
  const improved = direction === 'up' ? absolute > 0 : absolute < 0
  return improved ? 'success' : 'danger'
}

function comparisonRows(baseline, candidate) {
  const baselinePhases = Object.fromEntries(
    (baseline.phases || []).map((phase) => [phase.name, phase])
  )
  return (candidate.phases || []).flatMap((phase) => {
    const previous = baselinePhases[phase.name]
    if (!previous) return []
    const label = PHASE_LABELS[phase.name] || phase.name
    return [
      {
        key: `${phase.name}.mrr`,
        metric: 'mrr',
        label: `${label} — MRR`,
        baseline: previous.results?.mrr,
        candidate: phase.results?.mrr,
        format: formatScore,
        digits: 2,
      },
      {
        key: `${phase.name}.latency`,
        metric: 'latency',
        label: `${label} — mean latency`,
        baseline: previous.results?.mean_latency_ms,
        candidate: phase.results?.mean_latency_ms,
        format: formatMs,
        digits: 0,
        suffix: ' ms',
      },
    ].filter((row) => Number.isFinite(row.baseline) || Number.isFinite(row.candidate))
  })
}

/**
 * The comparison block: a baseline, whether it may be compared at all, what
 * changed between the two, and the deltas.
 *
 * The comparability verdict is computed before the rows and rendered before
 * them too. A delta between two runs that measured different corpora is not
 * a regression or an improvement; it is a category error, and the report
 * says so above the table rather than in a footnote under it.
 */
export function buildComparison(candidate, history = []) {
  if (!candidate?.benchmark_id) return null
  const baseline = selectBaseline(candidate, history)
  if (!baseline) {
    return { baseline: null, comparable: false, changes: [], rows: [], reason: 'no-baseline' }
  }
  const { compatible, warnings } = compatibility(baseline, candidate)
  return {
    baseline,
    comparable: compatible,
    changes: warnings.map((warning) => ({
      ...warning,
      baselineText: formatProvenanceValue(warning.baseline),
      candidateText: formatProvenanceValue(warning.candidate),
    })),
    rows: comparisonRows(baseline, candidate).map((row) => {
      const delta = deltaOf(row.baseline, row.candidate)
      return {
        ...row,
        baselineText: row.format(row.baseline),
        candidateText: row.format(row.candidate),
        deltaText: formatDelta(delta.absolute, row.digits, row.suffix || ''),
        deltaPercentText: formatDelta(delta.percentage, 1, '%'),
        // Only coloured when the comparison is valid *and* the metric has a
        // defined direction: a delta nobody can read as good or bad is left
        // in the default colour.
        tone: compatible ? deltaTone(row.metric, delta.absolute) : null,
      }
    }),
    reason: compatible ? null : 'incompatible',
  }
}

/**
 * Which settings two runs of the same kind disagree on.
 *
 * `unobserved` is excluded from the comparison and surfaced separately: it
 * is a list of what rag could not see, not a setting in its own right, and
 * two runs that both failed to capture the embedding model have not been
 * shown to share one.
 */
export function diffSnapshots(current, previous) {
  const keys = new Set([...Object.keys(current || {}), ...Object.keys(previous || {})])
  keys.delete('unobserved')
  return [...keys]
    .filter((key) => JSON.stringify(current?.[key]) !== JSON.stringify(previous?.[key]))
    .map((key) => ({ key, current: current?.[key], previous: previous?.[key] }))
}

// ---------------------------------------------------------------------------
// Items
// ---------------------------------------------------------------------------

/**
 * The stage one item was attributed to, or a dash.
 *
 * An item that did not fail and one from a run written before attribution
 * existed both render as `—`: the column says where a failure happened, and
 * inventing a stage for an item that has none would be the one thing this
 * table must not do.
 */
export function failureLabel(row) {
  const category = row?.failure_attribution?.category
  if (!category || category === 'none' || category === 'not_applicable') return EMPTY
  return labelFor(FAILURE_CATEGORY_LABELS, category)
}

export const SCORE_BANDS = [
  { id: 'all', label: 'Any result' },
  { id: 'strong', label: 'Hit at rank 1' },
  { id: 'weak', label: 'Hit below rank 1' },
  { id: 'miss', label: 'No labelled hit' },
]

/** Where an item's first labelled hit landed, as a band. */
export function itemBand(row) {
  if (row?.first_hit_rank === 1) return 'strong'
  if (Number.isFinite(row?.first_hit_rank)) return 'weak'
  return 'miss'
}

/**
 * Whether an item failed to execute, as opposed to scoring badly.
 *
 * A retrieval miss is not a failure here: it is a measurement, and folding
 * the two together is what makes a failure filter useless.
 */
export function isFailedItem(row) {
  return Boolean(row?.error) || (Boolean(row?.outcome) && row.outcome !== 'success')
}

/**
 * Worst-first ordering for the item view.
 *
 * Failures rank above misses, misses above weak hits, and unscoreable items
 * sink to the bottom — they are not retrieval failures, and putting them at
 * the top would bury the ones that are.
 */
export function worstFirst(rows) {
  const rank = (row) => {
    if (row?.error) return -1
    if (row?.skipped || row?.unscorable) return Number.POSITIVE_INFINITY
    return typeof row?.reciprocal_rank === 'number' ? row.reciprocal_rank : 0
  }
  return [...(rows || [])].sort((a, b) => rank(a) - rank(b))
}

/** The item view's filters, applied to the worst-first ordering. */
export function filterItems(rows, { search = '', failuresOnly = false, band = 'all' } = {}) {
  const needle = search.trim().toLowerCase()
  return worstFirst(rows).filter((row) => {
    if (failuresOnly && !isFailedItem(row)) return false
    if (band !== 'all' && itemBand(row) !== band) return false
    if (!needle) return true
    return (
      String(row?.item_id || '').toLowerCase().includes(needle) ||
      String(row?.query || '').toLowerCase().includes(needle)
    )
  })
}

// ---------------------------------------------------------------------------
// The report
// ---------------------------------------------------------------------------

/**
 * A benchmark run as a report.
 *
 * The human labels lead — profile, dataset, when, how long — and the
 * benchmark id stays as technical metadata. Nobody recognises their run by
 * a UUID; they recognise it by which profile they started and when.
 */
export function benchmarkReport(benchmark, dataset) {
  if (!benchmark?.benchmark_id) return null
  const validation = benchmark.label_validation || null
  const stages = benchmarkStages(benchmark, validation)
  const measurements = benchmarkMeasurements(benchmark)
  const primary = measurements[measurements.length - 1] || null
  const terminal = isTerminal(benchmark)
  const progress = benchmark.progress || {}

  return {
    kind: 'benchmark',
    id: benchmark.benchmark_id,
    idLabel: 'Benchmark id',
    label: PROFILES_BY_ID[benchmark.profile]?.label || benchmark.profile || 'Benchmark',
    kindLabel: 'Benchmark',
    status: benchmark.status,
    statusMeta: statusMeta(benchmark.status),
    terminal,
    startedAt: benchmark.started_at || benchmark.created_at,
    startedLabel: formatRunTimestamp(benchmark.started_at || benchmark.created_at),
    duration: formatDuration(benchmark.started_at || benchmark.created_at, benchmark.finished_at),
    dataset: {
      name: benchmark.dataset_name || dataset?.name || 'Golden set',
      version: benchmark.dataset_version ?? dataset?.dataset_version ?? null,
      sha: benchmark.dataset_sha256 || null,
      itemCount: progress.items_per_phase ?? dataset?.item_count ?? null,
    },
    stages,
    measurements,
    primary,
    kpis: kpiSummary(primary),
    quality: primary?.results?.answer_quality || null,
    attribution: primary?.results?.failure_attribution || null,
    configSnapshot: benchmark.config_snapshot || null,
    labelValidation: validation,
    progress,
    activePhase: (benchmark.phases || []).find((phase) => phase.status === 'running') || null,
    error: benchmark.error || null,
    raw: benchmark,
  }
}

/**
 * A single evaluation run as the same report.
 *
 * One measurement rather than a phase list, and the only report that owns
 * per-item rows: the benchmark keeps its items in the diagnostic archive,
 * not in the record the page polls.
 */
export function evaluationReport(run, dataset) {
  if (!run?.run_id) return null
  const validation = run.label_validation || null
  const results = run.results || {}
  const measurement = Object.keys(results).length
    ? {
        key: run.mode || 'retrieval',
        label: labelFor(EVAL_MODE_LABELS, run.mode || 'retrieval'),
        status: run.status,
        results,
        items: run.per_item || [],
      }
    : null
  const stages = executionFlow([
    validationStage(validation),
    {
      key: run.mode || 'retrieval',
      label: labelFor(EVAL_MODE_LABELS, run.mode || 'retrieval'),
      status: run.status,
      note: run.error || null,
      results,
    },
  ])

  return {
    kind: 'evaluation',
    id: run.run_id,
    idLabel: 'Run id',
    label: labelFor(EVAL_MODE_LABELS, run.mode || 'retrieval'),
    kindLabel: 'Single evaluation',
    status: run.status,
    statusMeta: statusMeta(run.status),
    terminal: ['completed', 'failed'].includes(run.status),
    startedAt: run.started_at,
    startedLabel: formatRunTimestamp(run.started_at),
    duration: formatDuration(run.started_at, run.finished_at),
    dataset: {
      name: dataset?.name || 'Golden set',
      version: run.dataset_version ?? null,
      sha: run.dataset_sha256 || null,
      itemCount: results.items_evaluated ?? dataset?.item_count ?? null,
      drifted: Boolean(dataset?.dataset_sha256) && dataset.dataset_sha256 !== run.dataset_sha256,
    },
    stages,
    measurements: measurement ? [measurement] : [],
    primary: measurement,
    kpis: kpiSummary(measurement),
    quality: results.answer_quality || null,
    attribution: results.failure_attribution || null,
    configSnapshot: run.config_snapshot || null,
    labelValidation: validation,
    matchMode: run.match_mode,
    items: run.per_item || [],
    error: run.error || null,
    raw: run,
  }
}
