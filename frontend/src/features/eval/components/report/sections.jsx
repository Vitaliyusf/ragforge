'use client'

import { AlertTriangle } from 'lucide-react'
import {
  CONFIG_SNAPSHOT_LABELS,
  DATASET_DRIFT_NOTE_KEY,
  EMPTY,
  EVAL_ANSWER_METRIC_LABELS,
  EVAL_K_VALUES,
  EVAL_METRIC_LABELS,
  FAILURE_CATEGORY_HELP_KEYS,
  FAILURE_CATEGORY_LABEL_KEYS,
  FAILURE_CATEGORY_ORDER,
  LABEL_CHECK_REASON_KEYS,
  MAX_STALE_IDS_SHOWN,
  NO_FAILURES_NOTE_KEY,
  STALE_LABEL_NOTE_KEY,
  UNCHECKED_LABELS_NOTE_KEY,
  UNOBSERVED_NOTE_KEY,
  UNRETRIEVABLE_LABEL_NOTE_KEY,
  UNVERSIONED_RUN_NOTE_KEY,
  formatCount,
  formatDecimal,
  formatFingerprint,
  formatPercent,
  formatScore,
  formatSetting,
  labelFor,
  translatedLabelFor,
} from '@/features/metrics/components/metricsConfig'
import { Callout, Cell, Fact, Note, Num, ReportTable, Row } from './primitives'
import { useI18n } from '@/i18n'

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
  const { t } = useI18n()
  const metrics = ['recall_at_k', 'precision_at_k', 'hit_rate_at_k']
  return (
    <ReportTable
      caption={t('evalReport.scoresCaption')}
      columns={[
        { key: 'metric', label: t('evalReport.metric') },
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
  const { t } = useI18n()
  const attributed = attribution?.items_attributed || 0
  if (!attributed) return null
  const counts = attribution?.counts || {}
  const present = FAILURE_CATEGORY_ORDER.filter((category) => counts[category] > 0)

  return (
    <>
      {present.length === 0 ? (
        <Note>{t(NO_FAILURES_NOTE_KEY)}</Note>
      ) : (
        <ReportTable
          caption={t('evalReport.failureCaption')}
          columns={[
            { key: 'stage', label: t('evalReport.stage') },
            { key: 'items', label: t('evalReport.items'), align: 'right' },
            { key: 'share', label: t('evalReport.share'), align: 'right' },
          ]}
        >
          {present.map((category) => (
            <Row key={category}>
              <th
                scope="row"
                className="py-1.5 pr-3 text-left font-normal"
                style={{ color: 'var(--fg)' }}
              >
                {translatedLabelFor(FAILURE_CATEGORY_LABEL_KEYS, category, t)}
                <span className="block text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                  {FAILURE_CATEGORY_HELP_KEYS[category] ? t(FAILURE_CATEGORY_HELP_KEYS[category]) : null}
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
        caption={t('evalReport.configDiffCaption')}
        columns={[
          { key: 'setting', label: t('evalReport.setting') },
          { key: 'previous', label: t('evalReport.previousRun') },
          { key: 'current', label: t('evalReport.thisRun') },
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
          {t(UNOBSERVED_NOTE_KEY)}{' '}
          {t('evalReport.unobservedAffects', {
            fields: unobserved.map((key) => labelFor(CONFIG_SNAPSHOT_LABELS, key)).join(', '),
          })}
        </p>
      )}
    </>
  )
}

/** The whole configuration snapshot a run scored under. */
export function ConfigSnapshot({ snapshot }) {
  const { t } = useI18n()
  const entries = Object.entries(snapshot || {}).filter(([key]) => key !== 'unobserved')
  if (!entries.length) return <Note>{t('evalReport.noSnapshot')}</Note>
  return (
    <ReportTable
      caption={t('evalReport.snapshotCaption')}
      columns={[
        { key: 'setting', label: t('evalReport.setting') },
        { key: 'value', label: t('evalReport.value') },
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
  const { t } = useI18n()
  const sha = run?.dataset_sha256
  if (!sha) {
    return (
      <p className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {t(UNVERSIONED_RUN_NOTE_KEY)}
      </p>
    )
  }
  const drifted = Boolean(dataset?.dataset_sha256) && dataset.dataset_sha256 !== sha
  return (
    <div className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
      <span>
        {t('evalReport.labelsScored', { version: run.dataset_version ?? EMPTY })}{' '}
        {/* A digest is an identifier: LTR in every locale. */}
        <code dir="ltr" title={sha} className="tabular-nums [unicode-bidi:isolate]">
          {formatFingerprint(sha)}
        </code>
      </span>
      {drifted && (
        <p className="mt-1" style={{ color: 'var(--warning)' }}>
          {t(DATASET_DRIFT_NOTE_KEY)}
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
  const { t } = useI18n()
  if (!validation) return null

  if (!validation.checked) {
    return (
      <Callout tone="warning" icon={AlertTriangle} title={t('evalReport.labelsNotVerified')}>
        <p>{t(UNCHECKED_LABELS_NOTE_KEY)}</p>
        {LABEL_CHECK_REASON_KEYS[validation.reason] && (
          <p className="mt-1">{t(LABEL_CHECK_REASON_KEYS[validation.reason])}</p>
        )}
        {validation.error && <p className="mt-1 font-mono text-[12px]">{validation.error}</p>}
      </Callout>
    )
  }

  const stale = validation.stale_label_count || 0
  const barred = validation.unretrievable_label_count || 0
  if (!stale && !barred) return null

  return (
    <Callout tone="danger" icon={AlertTriangle} title={t('evalReport.labelsGone')}>
      <p>{t(STALE_LABEL_NOTE_KEY)}</p>
      <dl className="mt-3 flex flex-wrap gap-6">
        <Fact label={t('evalReport.staleLabels')} value={formatCount(stale)} />
        <Fact label={t('evalReport.itemsAffected')} value={formatCount(validation.stale_item_count)} />
        {barred > 0 && (
          <Fact label={t('evalReport.excludedFromRetrieval')} value={formatCount(barred)} />
        )}
      </dl>
      <IdList label={t('evalReport.missingIds')} ids={validation.stale_ids} />
      {barred > 0 && (
        <>
          <IdList label={t('evalReport.unreachableIds')} ids={validation.unretrievable_ids} />
          <p className="mt-1">{t(UNRETRIEVABLE_LABEL_NOTE_KEY)}</p>
        </>
      )}
      {validation.truncated && (
        <p className="mt-1 text-[12px]">{t('evalReport.idsAreSample')}</p>
      )}
    </Callout>
  )
}

/** A capped, monospaced list of affected ids. */
function IdList({ label, ids }) {
  const shown = (ids || []).slice(0, MAX_STALE_IDS_SHOWN)
  if (!shown.length) return null
  return (
    // The ids themselves are identifiers and keep their own LTR run; the
    // label in front of them is copy.
    <p className="mt-2 font-mono text-[12px]">
      {label}:{' '}
      <span dir="ltr" className="[unicode-bidi:isolate]">{shown.join(', ')}</span>
      {(ids || []).length > shown.length ? ', …' : ''}
    </p>
  )
}
