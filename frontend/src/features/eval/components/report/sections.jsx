'use client'

import { AlertTriangle } from 'lucide-react'
import {
  CONFIG_SNAPSHOT_LABELS,
  DATASET_DRIFT_NOTE,
  EMPTY,
  EVAL_ANSWER_METRIC_LABELS,
  EVAL_K_VALUES,
  EVAL_METRIC_LABELS,
  FAILURE_CATEGORY_HELP,
  FAILURE_CATEGORY_LABELS,
  FAILURE_CATEGORY_ORDER,
  LABEL_CHECK_REASONS,
  MAX_STALE_IDS_SHOWN,
  NO_FAILURES_NOTE,
  STALE_LABEL_NOTE,
  UNCHECKED_LABELS_NOTE,
  UNOBSERVED_NOTE,
  UNRETRIEVABLE_LABEL_NOTE,
  UNVERSIONED_RUN_NOTE,
  formatCount,
  formatDecimal,
  formatFingerprint,
  formatPercent,
  formatScore,
  formatSetting,
  labelFor,
} from '@/features/metrics/components/metricsConfig'
import { Callout, Cell, Fact, Note, Num, ReportTable, Row } from './primitives'

/**
 * The evidence blocks behind the report's headline figures.
 *
 * Each one answers a single question — did the labels still exist, what did
 * the run score at every cutoff, where did the failures happen, what
 * changed between two runs — and each renders nothing at all when it has no
 * evidence, rather than an empty table with a confident heading.
 */

/** Recall, precision and hit rate at every cutoff the run reports. */
export function ScoresAtK({ results }) {
  const metrics = ['recall_at_k', 'precision_at_k', 'hit_rate_at_k']
  return (
    <ReportTable
      caption="Retrieval scores at each cutoff"
      columns={[
        { key: 'metric', label: 'Metric' },
        ...EVAL_K_VALUES.map((k) => ({ key: k, label: `k=${k}`, align: 'right' })),
      ]}
    >
      {metrics.map((metric) => (
        <Row key={metric}>
          <th
            scope="row"
            className="py-1.5 pr-3 text-left font-normal"
            style={{ color: 'var(--fg)' }}
          >
            {EVAL_METRIC_LABELS[metric]}
          </th>
          {EVAL_K_VALUES.map((k) => (
            <Num key={k}>{formatPercent(results?.[metric]?.[String(k)])}</Num>
          ))}
        </Row>
      ))}
    </ReportTable>
  )
}

/** The answer-quality figures behind the headline groundedness score. */
export function AnswerQualityDetail({ quality }) {
  if (!quality) return null
  return (
    <dl className="flex flex-wrap gap-6 text-[13px]">
      <Fact
        label={EVAL_ANSWER_METRIC_LABELS.groundedness}
        value={formatScore(quality.groundedness?.mean)}
      />
      <Fact
        label={EVAL_ANSWER_METRIC_LABELS.citation_precision}
        value={formatPercent(quality.citation_precision?.mean)}
      />
      <Fact
        label={EVAL_ANSWER_METRIC_LABELS.citation_recall}
        value={formatPercent(quality.citation_recall?.mean)}
      />
      <Fact
        label={EVAL_ANSWER_METRIC_LABELS.hallucination_rate}
        value={formatPercent(quality.hallucination_rate)}
      />
      <Fact
        label={EVAL_ANSWER_METRIC_LABELS.hallucination_severe_rate}
        value={formatPercent(quality.hallucination_severe_rate)}
      />
      <Fact
        label={EVAL_ANSWER_METRIC_LABELS.unsupported_claims}
        value={formatDecimal(quality.unsupported_claims?.mean)}
      />
      <Fact
        label={EVAL_ANSWER_METRIC_LABELS.items_judged}
        value={`${formatCount(quality.items_judged)} of ${formatCount(
          (quality.items_judged || 0) + (quality.items_unjudged || 0)
        )}`}
      />
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
        <Note>{NO_FAILURES_NOTE}</Note>
      ) : (
        <ReportTable
          caption="Failure counts by pipeline stage"
          columns={[
            { key: 'stage', label: 'Stage' },
            { key: 'items', label: 'Items', align: 'right' },
            { key: 'share', label: 'Share', align: 'right' },
          ]}
        >
          {present.map((category) => (
            <Row key={category}>
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
              <Num>{formatCount(counts[category])}</Num>
              <Num>{formatPercent(attribution?.rates?.[category])}</Num>
            </Row>
          ))}
        </ReportTable>
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

/** The settings two consecutive runs of the same kind disagreed on. */
export function ConfigDiff({ diff, unobserved }) {
  return (
    <>
      <ReportTable
        caption="Configuration differences between the last two runs"
        columns={[
          { key: 'setting', label: 'Setting' },
          { key: 'previous', label: 'Previous run' },
          { key: 'current', label: 'This run' },
        ]}
      >
        {diff.map((entry) => (
          <Row key={entry.key}>
            <th
              scope="row"
              className="py-1.5 pr-3 text-left font-normal"
              style={{ color: 'var(--fg)' }}
            >
              {labelFor(CONFIG_SNAPSHOT_LABELS, entry.key)}
            </th>
            <Cell>{formatSetting(entry.previous)}</Cell>
            <Cell className="font-medium" color="var(--warning)">
              {formatSetting(entry.current)}
            </Cell>
          </Row>
        ))}
      </ReportTable>
      {unobserved?.length > 0 && (
        <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {UNOBSERVED_NOTE} Affects:{' '}
          {unobserved.map((key) => labelFor(CONFIG_SNAPSHOT_LABELS, key)).join(', ')}.
        </p>
      )}
    </>
  )
}

/** The whole configuration snapshot a run scored under. */
export function ConfigSnapshot({ snapshot }) {
  const entries = Object.entries(snapshot || {}).filter(([key]) => key !== 'unobserved')
  if (!entries.length) return <Note>This run recorded no configuration snapshot.</Note>
  return (
    <ReportTable
      caption="The configuration this run scored under"
      columns={[
        { key: 'setting', label: 'Setting' },
        { key: 'value', label: 'Value' },
      ]}
    >
      {entries.map(([key, value]) => (
        <Row key={key}>
          <th
            scope="row"
            className="py-1.5 pr-3 text-left font-normal"
            style={{ color: 'var(--fg)' }}
          >
            {labelFor(CONFIG_SNAPSHOT_LABELS, key)}
          </th>
          <Cell>{formatSetting(value)}</Cell>
        </Row>
      ))}
    </ReportTable>
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
      <p className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {UNVERSIONED_RUN_NOTE}
      </p>
    )
  }
  const drifted = Boolean(dataset?.dataset_sha256) && dataset.dataset_sha256 !== sha
  return (
    <div className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
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
        <Fact label="Stale labels" value={formatCount(stale)} />
        <Fact label="Items affected" value={formatCount(validation.stale_item_count)} />
        {barred > 0 && (
          <Fact label="Excluded from retrieval" value={formatCount(barred)} />
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
