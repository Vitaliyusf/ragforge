'use client'

import { useMemo, useState } from 'react'
import { AlertTriangle, FlaskConical, Play, Trash2, Upload } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import EmptyState from '@/components/ui/EmptyState'
import { ConfirmModal } from '@/components/ui/Modal'
import Select, { SelectItem } from '@/components/ui/Select'
import StatCard from '@/components/ui/StatCard'
import TabSkeleton from '@/components/ui/TabSkeleton'
import { useEvalRuns } from '../hooks/useEvalRuns'
import GoldenSetImporter from './benchmark/GoldenSetImporter'
import BenchmarkCenter from './benchmark/BenchmarkCenter'
import TimeSeries from './charts/TimeSeries'
import {
  CONFIG_DIFF_NOTE,
  CONFIG_SNAPSHOT_LABELS,
  DATASET_DRIFT_NOTE,
  EMPTY,
  EVAL_ANSWER_METRIC_LABELS,
  EVAL_HISTORY_K,
  EVAL_K_VALUES,
  EVAL_METRIC_LABELS,
  EVAL_MODE_HELP,
  EVAL_MODE_LABELS,
  FAILURE_ATTRIBUTION_NOTE,
  FAILURE_CATEGORY_HELP,
  FAILURE_CATEGORY_LABELS,
  FAILURE_CATEGORY_ORDER,
  FILE_MATCH_NOTE,
  GOLDEN_SET_HELP,
  LABEL_CHECK_REASONS,
  LABELS_VERIFIED_NOTE,
  MATCH_MODE_LABELS,
  MAX_STALE_IDS_SHOWN,
  NO_FAILURES_NOTE,
  RUN_STATUS_LABELS,
  RUN_STATUS_VARIANTS,
  STALE_LABEL_NOTE,
  UNCHECKED_LABELS_NOTE,
  UNOBSERVED_NOTE,
  UNPRICED_MODEL_NOTE,
  UNRETRIEVABLE_LABEL_NOTE,
  UNSCORABLE_ITEM_NOTE,
  UNVERSIONED_RUN_NOTE,
  formatCost,
  formatCount,
  formatDecimal,
  formatFingerprint,
  formatMs,
  formatPercent,
  formatScore,
  formatSetting,
  formatTimestamp,
  labelFor,
} from './metricsConfig'

/** Rows of the Recall/Precision/Hit-rate table, in display order. */
const K_METRICS = ['recall_at_k', 'precision_at_k', 'hit_rate_at_k']

/** How many per-item rows the drill-down shows before it truncates. */
const MAX_ITEM_ROWS = 25

/**
 * Which settings two runs disagree on.
 *
 * `unobserved` is excluded from the comparison and surfaced separately: it
 * is a list of what rag could not see, not a setting in its own right, and
 * two runs that both failed to capture the embedding model have not been
 * shown to share one.
 */
export function diffSnapshots(current, previous) {
  const keys = new Set([
    ...Object.keys(current || {}),
    ...Object.keys(previous || {}),
  ])
  keys.delete('unobserved')
  return [...keys]
    .filter((key) => JSON.stringify(current?.[key]) !== JSON.stringify(previous?.[key]))
    .map((key) => ({ key, current: current?.[key], previous: previous?.[key] }))
}

/**
 * Worst-first ordering for the per-item drill-down.
 *
 * Failures rank above misses, misses above weak hits, and unscoreable items
 * sink to the bottom — they are not retrieval failures and putting them at
 * the top would bury the ones that are. An item excluded for stale labels
 * sinks for the same reason: its chunk is gone, which is a dataset problem,
 * not a ranking one.
 */
function worstFirst(rows) {
  const rank = (row) => {
    if (row?.error) return -1
    if (row?.skipped || row?.unscorable) return Number.POSITIVE_INFINITY
    return typeof row?.reciprocal_rank === 'number' ? row.reciprocal_rank : 0
  }
  return [...(rows || [])].sort((a, b) => rank(a) - rank(b))
}

/**
 * Completed runs as one Recall@5 series, oldest first.
 *
 * Returns nothing below two points. `TimeSeries` renders null for a single
 * point — one point is not a line — so passing it one would leave an empty
 * card where the panel should be saying why there is no trend yet.
 */
function historySeries(runs) {
  const points = (runs || [])
    .filter((entry) => entry?.status === 'completed')
    .map((entry) => [
      Date.parse(entry?.started_at),
      Number(entry?.results?.recall_at_k?.[EVAL_HISTORY_K]),
    ])
    .filter(([time, value]) => Number.isFinite(time) && Number.isFinite(value))
    .sort((a, b) => a[0] - b[0])
  return points.length >= 2 ? [{ name: `Recall@${EVAL_HISTORY_K}`, points }] : []
}

export default function EvalPanel() {
  const {
    datasets,
    datasetId,
    selectDataset,
    runs,
    run,
    running,
    loading,
    error,
    busy,
    startRun,
    estimateRunCost,
    importDataset,
    deleteDataset,
    refresh,
  } = useEvalRuns()

  const [importOpen, setImportOpen] = useState(false)
  const [mode, setMode] = useState('retrieval')
  // The estimate doubles as the confirmation gate: an end-to-end run cannot
  // start until one has been fetched and shown.
  const [estimate, setEstimate] = useState(null)
  const [estimating, setEstimating] = useState(false)

  const dataset = datasets.find((entry) => entry.dataset_id === datasetId)
  const series = useMemo(() => historySeries(runs), [runs])
  const configDiff = useMemo(
    () => (runs.length >= 2 ? diffSnapshots(runs[0]?.config_snapshot, runs[1]?.config_snapshot) : []),
    [runs]
  )

  /**
   * Start a retrieval run directly; price an end-to-end run first.
   *
   * A retrieval run calls no model and cannot cost anything, so a
   * confirmation there would be noise. An end-to-end run spends tokens per
   * item, and the number is shown before it can be started.
   */
  const handleRun = async () => {
    if (mode !== 'end_to_end') {
      await startRun('retrieval')
      return
    }
    setEstimating(true)
    // No model name is sent: the panel does not know which model rag will
    // use, so the estimate comes back flagged as unpriced rather than priced
    // against a guess. `estimateDescription` says so in words.
    const priced = await estimateRunCost(dataset?.item_count || 0, mode, null)
    setEstimating(false)
    if (priced) setEstimate(priced)
  }

  const confirmRun = async () => {
    setEstimate(null)
    await startRun('end_to_end')
  }

  if (loading && !datasets.length) return <TabSkeleton />

  if (!datasets.length) {
    return (
      <>
        <EmptyState
          icon={FlaskConical}
          title="No golden set yet"
          description={
            'Live traffic can only show proxy quality. Recall and nDCG need ' +
            'ground truth, which is a set of queries somebody labelled by hand.'
          }
          action={
            <div className="flex flex-col items-center gap-4">
              <ol
                className="max-w-md list-decimal space-y-1 pl-5 text-left text-[13px]"
                style={{ color: 'var(--fg-muted)' }}
              >
                {GOLDEN_SET_HELP.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
              <Button onClick={() => setImportOpen(true)} leftIcon={<Upload size={14} />}>
                Import a dataset
              </Button>
            </div>
          }
        />
        <GoldenSetImporter
          open={importOpen}
          onOpenChange={setImportOpen}
          onSubmit={importDataset}
          busy={busy}
          error={error}
        />
      </>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div
          className="flex items-center justify-between gap-3 rounded-xl px-4 py-3 text-[15px]"
          style={{
            background: 'var(--danger-soft)',
            border: '1px solid rgba(239,68,68,0.25)',
            color: 'var(--danger)',
          }}
        >
          <span className="flex items-center gap-2.5">
            <AlertTriangle size={15} />
            {error}
          </span>
          <Button variant="secondary" size="sm" onClick={refresh}>
            Retry
          </Button>
        </div>
      )}

      <Card>
        <CardHeader
          title="Golden set"
          description="Measured against hand-labelled ground truth, not live traffic."
          action={
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setImportOpen(true)}
                leftIcon={<Upload size={13} />}
              >
                Import
              </Button>
              <Select
                value={mode}
                onValueChange={setMode}
                className="w-[190px]"
                aria-label="Run mode"
              >
                {Object.entries(EVAL_MODE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </Select>
              <Button
                size="sm"
                onClick={handleRun}
                disabled={busy || running || estimating || !datasetId}
                leftIcon={<Play size={13} />}
              >
                {running ? 'Running…' : estimating ? 'Estimating…' : 'Run evaluation'}
              </Button>
            </div>
          }
        />

        <div className="flex flex-wrap items-end gap-4">
          <Select
            value={datasetId}
            onValueChange={selectDataset}
            className="w-[260px]"
            aria-label="Dataset"
          >
            {datasets.map((entry) => (
              <SelectItem key={entry.dataset_id} value={entry.dataset_id}>
                {entry.name}
              </SelectItem>
            ))}
          </Select>

          <dl className="flex flex-wrap items-end gap-6">
            <div>
              <dt className="label-xs">Items</dt>
              <dd className="mt-0.5 text-[15px] font-semibold tabular-nums">
                {formatCount(dataset?.item_count)}
              </dd>
            </div>
            <div>
              <dt className="label-xs">Last run</dt>
              <dd className="mt-0.5 text-[15px] font-semibold">
                {dataset?.last_run_at ? formatTimestamp(dataset.last_run_at) : EMPTY}
              </dd>
            </div>
            {run?.status && (
              <div>
                <dt className="label-xs">Status</dt>
                <dd className="mt-0.5">
                  <Badge variant={RUN_STATUS_VARIANTS[run.status] || 'default'} dot>
                    {labelFor(RUN_STATUS_LABELS, run.status)}
                  </Badge>
                </dd>
              </div>
            )}
          </dl>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => deleteDataset(datasetId)}
            disabled={busy || running || !datasetId}
            leftIcon={<Trash2 size={13} />}
          >
            Delete
          </Button>
        </div>

        <p className="mt-3 text-[13px]" style={{ color: 'var(--fg-muted)' }}>
          {EVAL_MODE_HELP[mode]}
        </p>

        {running && (
          <p className="mt-1 text-[13px]" style={{ color: 'var(--fg-muted)' }}>
            {formatCount(run?.per_item?.length || 0)} of {formatCount(dataset?.item_count)} items
            scored. {run?.mode === 'end_to_end'
              ? 'End-to-end — every item calls the model.'
              : 'Retrieval only — this run calls no language model.'}
          </p>
        )}

        {run?.run_id && <DatasetProvenance run={run} dataset={dataset} />}

        {run?.status === 'failed' && run?.error && (
          <p className="mt-3 text-[13px]" style={{ color: 'var(--danger)' }}>
            Run failed: {run.error}
          </p>
        )}
      </Card>

      <BenchmarkCenter datasetId={datasetId} datasetName={dataset?.name} ready={Boolean(datasetId)} />

      {run?.run_id && <LabelValidation validation={run.label_validation} />}

      {configDiff.length > 0 && (
        <ConfigDiff diff={configDiff} unobserved={runs[0]?.config_snapshot?.unobserved} />
      )}

      {run?.results && Object.keys(run.results).length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label={EVAL_METRIC_LABELS.mrr}
              value={formatScore(run.results.mrr)}
              subLabel="mean reciprocal rank of the first hit"
            />
            <StatCard
              label={EVAL_METRIC_LABELS.ndcg_at_10}
              value={formatScore(run.results.ndcg_at_k?.['10'])}
              subLabel="rewards ranking hits high, not just finding them"
            />
            <StatCard
              label={EVAL_METRIC_LABELS.items_evaluated}
              value={formatCount(run.results.items_evaluated)}
              // The denominator behind every mean above. A high recall over
              // three items is not a measurement of anything.
              subLabel={`${formatCount(run.results.items_skipped)} skipped, ${formatCount(
                run.results.items_unscorable
              )} unscorable, ${formatCount(run.results.items_failed)} failed`}
            />
            <StatCard
              label={EVAL_METRIC_LABELS.mean_latency_ms}
              value={formatMs(run.results.mean_latency_ms)}
              subLabel="per query, retrieval only"
            />
          </div>

          {run.results.answer_quality && (
            <AnswerQuality quality={run.results.answer_quality} />
          )}

          <Card>
            <CardHeader
              title="Scores at k"
              description={
                run.match_mode === 'file_id'
                  ? FILE_MATCH_NOTE
                  : `${labelFor(MATCH_MODE_LABELS, run.match_mode)} matching against the labelled ids.`
              }
            />
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <caption className="sr-only">Retrieval scores at each cutoff</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                      Metric
                    </th>
                    {EVAL_K_VALUES.map((k) => (
                      <th key={k} scope="col" className="py-1.5 pr-3 text-right font-medium">
                        k={k}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {K_METRICS.map((metric) => (
                    <tr key={metric} className="border-t" style={{ borderColor: 'var(--border)' }}>
                      <th
                        scope="row"
                        className="py-1.5 pr-3 text-left font-normal"
                        style={{ color: 'var(--fg)' }}
                      >
                        {EVAL_METRIC_LABELS[metric]}
                      </th>
                      {EVAL_K_VALUES.map((k) => (
                        <td
                          key={k}
                          className="py-1.5 pr-3 text-right tabular-nums"
                          style={{ color: 'var(--fg-muted)' }}
                        >
                          {formatPercent(run.results[metric]?.[String(k)])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <FailureAttribution attribution={run.results.failure_attribution} />
        </>
      )}

      <Card>
        <CardHeader
          title={`Recall@${EVAL_HISTORY_K} over time`}
          description="A retrieval config change should show up here as a step."
        />
        {series.length ? (
          <TimeSeries
            series={series}
            label={`Recall@${EVAL_HISTORY_K} by run`}
            yFormat={(value) => formatPercent(value)}
          />
        ) : (
          <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
            Two completed runs are needed before a trend can be drawn.
          </p>
        )}
      </Card>

      {run?.per_item?.length > 0 && <ItemTable rows={run.per_item} />}

      <ConfirmModal
        open={Boolean(estimate)}
        onOpenChange={(next) => {
          if (!next) setEstimate(null)
        }}
        title="Start an end-to-end run?"
        description={estimateDescription(estimate)}
        confirmLabel="Run anyway"
        onConfirm={confirmRun}
      />

      <GoldenSetImporter
        open={importOpen}
        onOpenChange={setImportOpen}
        onSubmit={importDataset}
        busy={busy}
        error={error}
      />
    </div>
  )
}

/**
 * The sentence shown before an end-to-end run starts.
 *
 * States the estimate as an estimate, and says plainly when a $0.00 figure
 * means "this model has no configured price" rather than "this is free".
 */
export function estimateDescription(estimate) {
  if (!estimate) return ''
  const tokens = (estimate.estimated_tokens_in || 0) + (estimate.estimated_tokens_out || 0)
  const base =
    `${formatCount(estimate.item_count)} items × ${estimate.calls_per_item} model calls ` +
    `≈ ${formatCount(tokens)} tokens, an estimated ${formatCost(estimate.estimated_cost_usd)}. ` +
    'This run also takes minutes rather than seconds.'
  return estimate.model_priced ? base : `${base} ${UNPRICED_MODEL_NOTE}`
}

/**
 * Which label set the displayed run actually scored.
 *
 * A `dataset_id` is not evidence on its own — the items behind it can be
 * replaced — so the run's own snapshot of the version and fingerprint is
 * what makes two runs comparable, or provably not. The digest is abbreviated
 * for reading and kept whole in the title for copying.
 *
 * A run written before versioning existed reports neither, and says so
 * rather than borrowing the dataset's current values: those would describe
 * labels the run may never have seen.
 */
export function DatasetProvenance({ run, dataset }) {
  const sha = run?.dataset_sha256
  if (!sha) {
    return (
      <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {UNVERSIONED_RUN_NOTE}
      </p>
    )
  }
  const drifted = Boolean(dataset?.dataset_sha256) && dataset.dataset_sha256 !== sha
  return (
    <div className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
      <span>
        Labels scored: version {run.dataset_version ?? EMPTY}, fingerprint{' '}
        <code title={sha} className="tabular-nums">
          {formatFingerprint(sha)}
        </code>
      </span>
      {drifted && (
        <p className="mt-1" style={{ color: 'var(--warning)' }}>
          {DATASET_DRIFT_NOTE}
        </p>
      )}
    </div>
  )
}

/**
 * Whether this run's ground truth still exists in the live index.
 *
 * The panel's job here is to keep two things apart that a recall number
 * cannot: retrieval failed to rank a chunk that is there, versus the chunk
 * is gone and no retriever could have found it. The second one is a dataset
 * problem, and reading it as a regression is how a team spends a week
 * tuning a retriever that never broke.
 *
 * A run recorded before this check existed carries no validation at all and
 * renders nothing, rather than claiming its labels were fine.
 */
export function LabelValidation({ validation }) {
  if (!validation) return null

  if (!validation.checked) {
    return (
      <Callout tone="warning" icon={AlertTriangle} title="Labels were not verified">
        <p>{UNCHECKED_LABELS_NOTE}</p>
        {LABEL_CHECK_REASONS[validation.reason] && (
          <p className="mt-1">{LABEL_CHECK_REASONS[validation.reason]}</p>
        )}
        {validation.error && (
          <p className="mt-1 font-mono text-[12px]">{validation.error}</p>
        )}
      </Callout>
    )
  }

  const stale = validation.stale_label_count || 0
  const barred = validation.unretrievable_label_count || 0
  if (!stale && !barred) {
    return (
      <p className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {LABELS_VERIFIED_NOTE}
      </p>
    )
  }

  return (
    <Callout tone="danger" icon={AlertTriangle} title="Benchmark labels no longer exist">
      <p>{STALE_LABEL_NOTE}</p>
      <dl className="mt-3 flex flex-wrap gap-6">
        <div>
          <dt className="label-xs">Stale labels</dt>
          <dd className="mt-0.5 font-semibold tabular-nums">{formatCount(stale)}</dd>
        </div>
        <div>
          <dt className="label-xs">Items affected</dt>
          <dd className="mt-0.5 font-semibold tabular-nums">
            {formatCount(validation.stale_item_count)}
          </dd>
        </div>
        {barred > 0 && (
          <div>
            <dt className="label-xs">Excluded from retrieval</dt>
            <dd className="mt-0.5 font-semibold tabular-nums">{formatCount(barred)}</dd>
          </div>
        )}
      </dl>
      <IdList label="Missing ids" ids={validation.stale_ids} />
      {barred > 0 && (
        <>
          <IdList label="Unreachable ids" ids={validation.unretrievable_ids} />
          <p className="mt-1">{UNRETRIEVABLE_LABEL_NOTE}</p>
        </>
      )}
      {validation.truncated && (
        <p className="mt-1 text-[12px]">
          The counts above are exact; the ids are a sample.
        </p>
      )}
    </Callout>
  )
}

/** A capped, monospaced list of affected ids. */
function IdList({ label, ids }) {
  const shown = (ids || []).slice(0, MAX_STALE_IDS_SHOWN)
  if (!shown.length) return null
  return (
    <p className="mt-2 font-mono text-[12px]">
      {label}: {shown.join(', ')}
      {(ids || []).length > shown.length ? ', …' : ''}
    </p>
  )
}

/** A bordered notice in one of the panel's two alert tones. */
function Callout({ tone, icon: Icon, title, children }) {
  const color = tone === 'danger' ? 'var(--danger)' : 'var(--warning)'
  return (
    <div
      className="rounded-xl px-4 py-3 text-[13px]"
      style={{
        background: tone === 'danger' ? 'var(--danger-soft)' : 'var(--warning-soft)',
        border: `1px solid ${color}40`,
        color,
      }}
    >
      <p className="flex items-center gap-2 text-[15px] font-semibold">
        <Icon size={15} />
        {title}
      </p>
      <div className="mt-1.5">{children}</div>
    </div>
  )
}

/** Answer-quality results, shown only for an end-to-end run. */
function AnswerQuality({ quality }) {
  const judged = quality?.items_judged ?? 0
  const unjudged = quality?.items_unjudged ?? 0
  return (
    <Card>
      <CardHeader
        title="Answer quality"
        description="From the same judge the live pipeline uses. Items it could not judge are excluded from every figure below, never counted as passes."
      />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label={EVAL_ANSWER_METRIC_LABELS.groundedness}
          value={formatScore(quality?.groundedness?.mean)}
          subLabel={`over ${formatCount(quality?.groundedness?.counted)} items`}
        />
        <StatCard
          label={EVAL_ANSWER_METRIC_LABELS.hallucination_rate}
          value={formatPercent(quality?.hallucination_rate)}
          subLabel={`${formatCount(judged)} judged, ${formatCount(unjudged)} unjudged`}
        />
        <StatCard
          label={EVAL_ANSWER_METRIC_LABELS.citation_precision}
          value={formatPercent(quality?.citation_precision?.mean)}
          subLabel={`${formatCount(quality?.citation_precision?.excluded)} cited nothing`}
        />
        <StatCard
          label={EVAL_ANSWER_METRIC_LABELS.citation_recall}
          value={formatPercent(quality?.citation_recall?.mean)}
          subLabel={`over ${formatCount(quality?.citation_recall?.counted)} items`}
        />
      </div>
      <dl className="mt-4 flex flex-wrap gap-6 text-[13px]">
        <div>
          <dt className="label-xs">{EVAL_ANSWER_METRIC_LABELS.hallucination_severe_rate}</dt>
          <dd className="mt-0.5 font-semibold tabular-nums">
            {formatPercent(quality?.hallucination_severe_rate)}
          </dd>
        </div>
        <div>
          <dt className="label-xs">{EVAL_ANSWER_METRIC_LABELS.unsupported_claims}</dt>
          <dd className="mt-0.5 font-semibold tabular-nums">
            {formatDecimal(quality?.unsupported_claims?.mean)}
          </dd>
        </div>
      </dl>
    </Card>
  )
}

/**
 * Where the run's failures happened, counted by stage.
 *
 * Only the categories that actually occurred are listed: eleven rows of
 * mostly zeroes hides the two that matter. Nothing is rendered at all when
 * no item could be attributed — a run with no labelled items has not been
 * shown to be clean, and a table of dashes would imply it had.
 */
export function FailureAttribution({ attribution }) {
  const attributed = attribution?.items_attributed || 0
  if (!attributed) return null
  const counts = attribution?.counts || {}
  const present = FAILURE_CATEGORY_ORDER.filter((category) => counts[category] > 0)

  return (
    <Card>
      <CardHeader title="Where the failures were" description={FAILURE_ATTRIBUTION_NOTE} />
      {present.length === 0 ? (
        <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
          {NO_FAILURES_NOTE}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <caption className="sr-only">Failure counts by pipeline stage</caption>
            <thead>
              <tr style={{ color: 'var(--fg-muted)' }}>
                <th scope="col" className="py-1.5 pr-3 text-left font-medium">Stage</th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">Items</th>
                <th scope="col" className="py-1.5 text-right font-medium">Share</th>
              </tr>
            </thead>
            <tbody>
              {present.map((category) => (
                <tr key={category} className="border-t align-top" style={{ borderColor: 'var(--border)' }}>
                  <th scope="row" className="py-1.5 pr-3 text-left font-normal" style={{ color: 'var(--fg)' }}>
                    {labelFor(FAILURE_CATEGORY_LABELS, category)}
                    <span className="block text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                      {FAILURE_CATEGORY_HELP[category]}
                    </span>
                  </th>
                  <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                    {formatCount(counts[category])}
                  </td>
                  <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                    {formatPercent(attribution?.rates?.[category])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {formatCount(attributed)} items attributed —{' '}
        {formatCount(attribution?.items_without_failure)} with no failure,{' '}
        {formatCount(attribution?.items_unclassified)} without enough evidence to place.
        Unlabelled items are excluded from every share above.
      </p>
    </Card>
  )
}

/** The settings two consecutive runs disagreed on. */
function ConfigDiff({ diff, unobserved }) {
  return (
    <Card>
      <CardHeader title="Configuration changed between runs" description={CONFIG_DIFF_NOTE} />
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <caption className="sr-only">Configuration differences between the last two runs</caption>
          <thead>
            <tr style={{ color: 'var(--fg-muted)' }}>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">Setting</th>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">Previous run</th>
              <th scope="col" className="py-1.5 text-left font-medium">This run</th>
            </tr>
          </thead>
          <tbody>
            {diff.map((entry) => (
              <tr key={entry.key} className="border-t" style={{ borderColor: 'var(--border)' }}>
                <th scope="row" className="py-1.5 pr-3 text-left font-normal" style={{ color: 'var(--fg)' }}>
                  {labelFor(CONFIG_SNAPSHOT_LABELS, entry.key)}
                </th>
                <td className="py-1.5 pr-3" style={{ color: 'var(--fg-muted)' }}>
                  {formatSetting(entry.previous)}
                </td>
                <td className="py-1.5 font-medium" style={{ color: 'var(--warning)' }}>
                  {formatSetting(entry.current)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {unobserved?.length > 0 && (
        <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {UNOBSERVED_NOTE} Affects:{' '}
          {unobserved.map((key) => labelFor(CONFIG_SNAPSHOT_LABELS, key)).join(', ')}.
        </p>
      )}
    </Card>
  )
}

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

/** Per-item drill-down, worst first — the failures are the point. */
function ItemTable({ rows }) {
  const ordered = useMemo(() => worstFirst(rows), [rows])
  const shown = ordered.slice(0, MAX_ITEM_ROWS)

  return (
    <Card>
      <CardHeader
        title="Per-item results"
        description="Worst first. A missing rank means retrieval never returned a labelled chunk — unless the row says the label itself is gone."
      />
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <caption className="sr-only">Per-item retrieval results, worst first</caption>
          <thead>
            <tr style={{ color: 'var(--fg-muted)' }}>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">Query</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">First hit</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Recall@10</th>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">Lost at</th>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">Expected</th>
              <th scope="col" className="py-1.5 text-left font-medium">Retrieved</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.item_id} className="border-t align-top" style={{ borderColor: 'var(--border)' }}>
                <th scope="row" className="py-1.5 pr-3 text-left font-normal" style={{ color: 'var(--fg)' }}>
                  {row.query}
                  {row.error && (
                    <span className="ml-2 text-[12px]" style={{ color: 'var(--danger)' }}>
                      failed: {row.error}
                    </span>
                  )}
                  {row.skipped && !row.error && (
                    <span className="ml-2 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                      not labelled — excluded from every average
                    </span>
                  )}
                  {row.unscorable && !row.error && (
                    <span className="ml-2 text-[12px]" style={{ color: 'var(--warning)' }}>
                      {UNSCORABLE_ITEM_NOTE}
                    </span>
                  )}
                </th>
                <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                  {row.first_hit_rank ?? EMPTY}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                  {formatPercent(row.recall_at_10)}
                </td>
                <td className="py-1.5 pr-3" style={{ color: 'var(--fg-muted)' }}>
                  {failureLabel(row)}
                </td>
                <td className="py-1.5 pr-3 font-mono text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                  {(row.expected_ids || []).join(', ') || EMPTY}
                </td>
                <td className="py-1.5 font-mono text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                  {(row.retrieved_ids || []).join(', ') || EMPTY}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {ordered.length > shown.length && (
        <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          Showing the {MAX_ITEM_ROWS} worst of {formatCount(ordered.length)} items.
        </p>
      )}
    </Card>
  )
}
