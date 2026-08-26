'use client'

import { useMemo } from 'react'
import { AlertTriangle, ChevronRight } from 'lucide-react'
import Card, { CardHeader } from '@/components/ui/Card'
import StatCard from '@/components/ui/StatCard'
import TimeSeries from '@/features/metrics/components/charts/TimeSeries'
import {
  CONFIG_DIFF_NOTE,
  CONFIG_SNAPSHOT_LABELS,
  DATASET_DRIFT_NOTE,
  EMPTY,
  EVAL_ANSWER_METRIC_LABELS,
  EVAL_HISTORY_K,
  EVAL_K_VALUES,
  EVAL_METRIC_LABELS,
  FAILURE_ATTRIBUTION_NOTE,
  FAILURE_CATEGORY_HELP,
  FAILURE_CATEGORY_LABELS,
  FAILURE_CATEGORY_ORDER,
  FILE_MATCH_NOTE,
  LABEL_CHECK_REASONS,
  LABELS_VERIFIED_NOTE,
  MATCH_MODE_LABELS,
  MAX_STALE_IDS_SHOWN,
  NO_FAILURES_NOTE,
  STALE_LABEL_NOTE,
  UNCHECKED_LABELS_NOTE,
  UNOBSERVED_NOTE,
  UNRETRIEVABLE_LABEL_NOTE,
  UNSCORABLE_ITEM_NOTE,
  UNVERSIONED_RUN_NOTE,
  formatCount,
  formatDecimal,
  formatFingerprint,
  formatMs,
  formatPercent,
  formatScore,
  formatSetting,
  labelFor,
} from '@/features/metrics/components/metricsConfig'

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
  const keys = new Set([...Object.keys(current || {}), ...Object.keys(previous || {})])
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
 * card where the page should be saying why there is no trend yet.
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

/**
 * What the displayed run measured.
 *
 * The headline scores and any warning about the ground truth are always
 * visible; everything else — the tables, the snapshots, the per-item
 * drill-down — sits behind a disclosure. The evidence is all still here,
 * but a page that renders eleven tables at once is a page nobody reads.
 */
export default function EvalResults({ run, runs = [], dataset }) {
  const series = useMemo(() => historySeries(runs), [runs])
  const configDiff = useMemo(
    () =>
      runs.length >= 2
        ? diffSnapshots(runs[0]?.config_snapshot, runs[1]?.config_snapshot)
        : [],
    [runs]
  )

  if (!run?.run_id) return null

  const results = run.results || {}
  const quality = results.answer_quality
  const measured = Object.keys(results).length > 0

  return (
    <div className="flex flex-col gap-4">
      {/* Warnings first, and never behind a disclosure: a score that rests
          on labels the index no longer holds is the one thing on this page
          that must not be scrolled past. */}
      <LabelValidation validation={run.label_validation} />

      {run.status === 'failed' && run.error && (
        <Callout tone="danger" icon={AlertTriangle} title="Evaluation run failed">
          <p>{run.error}</p>
        </Callout>
      )}

      {measured && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatCard
              label={EVAL_METRIC_LABELS.mrr}
              value={formatScore(results.mrr)}
              subLabel="mean reciprocal rank of the first hit"
            />
            <StatCard
              label={`Recall@${EVAL_HISTORY_K}`}
              value={formatPercent(results.recall_at_k?.[EVAL_HISTORY_K])}
              subLabel="labelled chunks found in the top five"
            />
            <StatCard
              label={EVAL_METRIC_LABELS.ndcg_at_10}
              value={formatScore(results.ndcg_at_k?.['10'])}
              subLabel="rewards ranking hits high, not just finding them"
            />
            <StatCard
              label={EVAL_METRIC_LABELS.items_evaluated}
              value={formatCount(results.items_evaluated)}
              // The denominator behind every mean above. A high recall over
              // three items is not a measurement of anything.
              subLabel={`${formatCount(results.items_skipped)} skipped, ${formatCount(
                results.items_unscorable
              )} unscorable, ${formatCount(results.items_failed)} failed`}
            />
            <StatCard
              label={EVAL_METRIC_LABELS.mean_latency_ms}
              value={formatMs(results.mean_latency_ms)}
              subLabel="per query, retrieval only"
            />
          </div>

          {quality && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard
                label={EVAL_ANSWER_METRIC_LABELS.groundedness}
                value={formatScore(quality.groundedness?.mean)}
                subLabel={`over ${formatCount(quality.groundedness?.counted)} items`}
              />
              <StatCard
                label={EVAL_ANSWER_METRIC_LABELS.citation_precision}
                value={formatPercent(quality.citation_precision?.mean)}
                subLabel={`${formatCount(quality.citation_precision?.excluded)} cited nothing`}
              />
              <StatCard
                label={EVAL_ANSWER_METRIC_LABELS.citation_recall}
                value={formatPercent(quality.citation_recall?.mean)}
                subLabel={`over ${formatCount(quality.citation_recall?.counted)} items`}
              />
              <StatCard
                label={EVAL_ANSWER_METRIC_LABELS.hallucination_rate}
                value={formatPercent(quality.hallucination_rate)}
                subLabel={`${formatCount(quality.items_judged)} judged, ${formatCount(
                  quality.items_unjudged
                )} unjudged`}
              />
            </div>
          )}
        </>
      )}

      <Card padding="sm">
        <CardHeader
          className="mb-2"
          title="Run details"
          description="Open a section for the evidence behind the figures above."
        />

        <DatasetProvenance run={run} dataset={dataset} />

        {measured && (
          <Disclosure
            title="Scores at k"
            summary={
              run.match_mode === 'file_id'
                ? FILE_MATCH_NOTE
                : `${labelFor(MATCH_MODE_LABELS, run.match_mode)} matching against the labelled ids.`
            }
          >
            <ScoresAtK results={results} />
          </Disclosure>
        )}

        {quality && (
          <Disclosure
            title="Answer quality"
            summary="From the same judge the live pipeline uses. Items it could not judge are excluded from every figure, never counted as passes."
          >
            <AnswerQualityDetail quality={quality} />
          </Disclosure>
        )}

        {run.label_validation?.checked && !hasStaleLabels(run.label_validation) && (
          <Disclosure title="Validation" summary="Ground truth checked against the live index.">
            <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
              {LABELS_VERIFIED_NOTE}
            </p>
          </Disclosure>
        )}

        {configDiff.length > 0 && (
          <Disclosure
            title="Configuration changed between runs"
            summary={CONFIG_DIFF_NOTE}
            tone="warning"
          >
            <ConfigDiff diff={configDiff} unobserved={runs[0]?.config_snapshot?.unobserved} />
          </Disclosure>
        )}

        {results.failure_attribution?.items_attributed > 0 && (
          <Disclosure title="Failure attribution" summary={FAILURE_ATTRIBUTION_NOTE}>
            <FailureAttribution attribution={results.failure_attribution} />
          </Disclosure>
        )}

        {run.per_item?.length > 0 && (
          <Disclosure
            title="Per-item results"
            summary="Worst first. A missing rank means retrieval never returned a labelled chunk — unless the row says the label itself is gone."
          >
            <ItemTable rows={run.per_item} />
          </Disclosure>
        )}

        <Disclosure
          title={`Recall@${EVAL_HISTORY_K} over time`}
          summary="A retrieval config change should show up here as a step."
        >
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
        </Disclosure>
      </Card>
    </div>
  )
}

function hasStaleLabels(validation) {
  return Boolean(validation?.stale_label_count || validation?.unretrievable_label_count)
}

/**
 * One collapsible detail section.
 *
 * `<details>` rather than a bespoke accordion: it is keyboard-operable,
 * announced correctly and findable by the browser's own in-page search
 * without any of that having to be written or tested here.
 */
function Disclosure({ title, summary, tone, defaultOpen = false, children }) {
  return (
    <details
      className="group border-t"
      style={{ borderColor: 'var(--border)' }}
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none items-start gap-2 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
        <ChevronRight
          size={14}
          aria-hidden="true"
          className="mt-0.5 shrink-0 transition-transform duration-150 group-open:rotate-90"
          style={{ color: 'var(--fg-soft)' }}
        />
        <span className="min-w-0">
          <span
            className="block text-[13px] font-medium"
            style={{ color: tone === 'warning' ? 'var(--warning)' : 'var(--fg)' }}
          >
            {title}
          </span>
          {summary && (
            <span className="mt-0.5 block text-[12px]" style={{ color: 'var(--fg-soft)' }}>
              {summary}
            </span>
          )}
        </span>
      </summary>
      <div className="pb-4 pl-6">{children}</div>
    </details>
  )
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
      <p className="pb-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {UNVERSIONED_RUN_NOTE}
      </p>
    )
  }
  const drifted = Boolean(dataset?.dataset_sha256) && dataset.dataset_sha256 !== sha
  return (
    <div className="pb-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
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
 * The job here is to keep two things apart that a recall number cannot:
 * retrieval failed to rank a chunk that is there, versus the chunk is gone
 * and no retriever could have found it. The second one is a dataset
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
        {validation.error && <p className="mt-1 font-mono text-[12px]">{validation.error}</p>}
      </Callout>
    )
  }

  const stale = validation.stale_label_count || 0
  const barred = validation.unretrievable_label_count || 0
  if (!stale && !barred) return null

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
        <p className="mt-1 text-[12px]">The counts above are exact; the ids are a sample.</p>
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

/** A bordered notice in one of the page's two alert tones. */
export function Callout({ tone, icon: Icon, title, children }) {
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
        <Icon size={15} aria-hidden="true" />
        {title}
      </p>
      <div className="mt-1.5">{children}</div>
    </div>
  )
}

/** Recall, precision and hit rate at every cutoff the run reports. */
function ScoresAtK({ results }) {
  return (
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
                  {formatPercent(results[metric]?.[String(k)])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The answer-quality figures that did not fit the headline row. */
function AnswerQualityDetail({ quality }) {
  return (
    <dl className="flex flex-wrap gap-6 text-[13px]">
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
      <div>
        <dt className="label-xs">{EVAL_ANSWER_METRIC_LABELS.items_judged}</dt>
        <dd className="mt-0.5 font-semibold tabular-nums">
          {formatCount(quality?.items_judged)}
        </dd>
      </div>
    </dl>
  )
}

/**
 * Where the run's failures happened, counted by stage.
 *
 * Only the categories that actually occurred are listed: eleven rows of
 * mostly zeroes hides the two that matter.
 */
export function FailureAttribution({ attribution }) {
  const attributed = attribution?.items_attributed || 0
  if (!attributed) return null
  const counts = attribution?.counts || {}
  const present = FAILURE_CATEGORY_ORDER.filter((category) => counts[category] > 0)

  return (
    <>
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
                <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                  Stage
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  Items
                </th>
                <th scope="col" className="py-1.5 text-right font-medium">
                  Share
                </th>
              </tr>
            </thead>
            <tbody>
              {present.map((category) => (
                <tr
                  key={category}
                  className="border-t align-top"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <th
                    scope="row"
                    className="py-1.5 pr-3 text-left font-normal"
                    style={{ color: 'var(--fg)' }}
                  >
                    {labelFor(FAILURE_CATEGORY_LABELS, category)}
                    <span className="block text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                      {FAILURE_CATEGORY_HELP[category]}
                    </span>
                  </th>
                  <td
                    className="py-1.5 pr-3 text-right tabular-nums"
                    style={{ color: 'var(--fg-muted)' }}
                  >
                    {formatCount(counts[category])}
                  </td>
                  <td
                    className="py-1.5 text-right tabular-nums"
                    style={{ color: 'var(--fg-muted)' }}
                  >
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
    </>
  )
}

/** The settings two consecutive runs disagreed on. */
function ConfigDiff({ diff, unobserved }) {
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <caption className="sr-only">
            Configuration differences between the last two runs
          </caption>
          <thead>
            <tr style={{ color: 'var(--fg-muted)' }}>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                Setting
              </th>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                Previous run
              </th>
              <th scope="col" className="py-1.5 text-left font-medium">
                This run
              </th>
            </tr>
          </thead>
          <tbody>
            {diff.map((entry) => (
              <tr key={entry.key} className="border-t" style={{ borderColor: 'var(--border)' }}>
                <th
                  scope="row"
                  className="py-1.5 pr-3 text-left font-normal"
                  style={{ color: 'var(--fg)' }}
                >
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
    </>
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
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <caption className="sr-only">Per-item retrieval results, worst first</caption>
          <thead>
            <tr style={{ color: 'var(--fg-muted)' }}>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                Query
              </th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                First hit
              </th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                Recall@10
              </th>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                Lost at
              </th>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                Expected
              </th>
              <th scope="col" className="py-1.5 text-left font-medium">
                Retrieved
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr
                key={row.item_id}
                className="border-t align-top"
                style={{ borderColor: 'var(--border)' }}
              >
                <th
                  scope="row"
                  className="py-1.5 pr-3 text-left font-normal"
                  style={{ color: 'var(--fg)' }}
                >
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
                <td
                  className="py-1.5 pr-3 text-right tabular-nums"
                  style={{ color: 'var(--fg-muted)' }}
                >
                  {row.first_hit_rank ?? EMPTY}
                </td>
                <td
                  className="py-1.5 pr-3 text-right tabular-nums"
                  style={{ color: 'var(--fg-muted)' }}
                >
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
    </>
  )
}
