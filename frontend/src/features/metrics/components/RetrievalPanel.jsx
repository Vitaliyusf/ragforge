'use client'

import { AlertTriangle, Search } from 'lucide-react'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import EmptyState from '@/components/feedback/EmptyState'
import TabSkeleton from '@/components/ui/TabSkeleton'
import Histogram from './charts/Histogram'
import {
  EMPTY,
  FILTER_REASON_LABEL_KEYS,
  METRIC_LABELS,
  PROM_UNAVAILABLE,
  formatCount,
  formatDecimal,
  formatPercent,
  formatScore,
  formatSeconds,
  labelFor,
  translatedLabelFor,
  thresholdVariant,
} from './metricsConfig'
import { useI18n } from '@/i18n'

const VARIANT_COLORS = {
  default: 'var(--fg)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
}

/** `{bucket, count}` from either backend into the chart's `{label, count}`. */
function toBuckets(rows) {
  return (rows || []).map((row) => ({
    label: String(row?.bucket ?? ''),
    count: Number(row?.count) || 0,
  }))
}

/** `{key: value}` into sorted rows, largest first. */
function toRows(map) {
  return Object.entries(map || {})
    .filter(([, value]) => Number.isFinite(Number(value)))
    .map(([key, value]) => ({ key, value: Number(value) }))
    .sort((a, b) => b.value - a.value)
}

/**
 * Wrap one Prometheus-backed widget.
 *
 * The unavailable state is per widget, never per panel: a monitoring outage
 * must not blank the MongoDB-backed figures rendered beside it.
 */
function PromWidget({ promAvailable, children }) {
  const { t } = useI18n()
  if (promAvailable) return children
  return (
    <EmptyState
      icon={AlertTriangle}
      size="sm"
      title={t(PROM_UNAVAILABLE.titleKey)}
      description={t(PROM_UNAVAILABLE.descriptionKey)}
    />
  )
}

function Stat({ label, value, hint, variant = 'default' }) {
  return (
    <div>
      <dt className="label-xs">{label}</dt>
      <dd
        className="mt-0.5 text-lg font-semibold tabular-nums"
        style={{ color: VARIANT_COLORS[variant] || VARIANT_COLORS.default }}
      >
        {value}
      </dd>
      {hint && (
        <p className="mt-0.5 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {hint}
        </p>
      )}
    </div>
  )
}

/**
 * Retrieval-quality panel.
 *
 * Mixes two backends and says which is which: hit rate, chunk counts and the
 * score distributions are tenant-scoped per-turn facts from MongoDB, while the
 * vector-search, reranker-latency and filtered-out figures come from Prometheus
 * and are platform-wide. Prometheus-backed widgets degrade individually.
 *
 * There is no context-utilisation widget: knowing how much retrieved context an
 * answer actually used requires citations, which the app does not emit yet.
 */
export default function RetrievalPanel({ data, loading, error, promAvailable = true, onRetry }) {
  const { t } = useI18n()
  if (loading && !data) return <TabSkeleton />

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title={t('retrieval.loadFailed')}
        description={error}
        action={onRetry ? <Button onClick={onRetry}>{t('common.retry')}</Button> : undefined}
      />
    )
  }

  // No traffic is an empty state, not a page of zeroes and NaN%. Checked on
  // `turns` from MongoDB rather than on Prometheus, which is platform-wide and
  // may well be busy while this tenant was idle.
  if (!data || !data.turns) {
    return (
      <EmptyState
        icon={Search}
        title={t('retrieval.noActivity')}
        description={t('retrieval.noActivityDescription')}
      />
    )
  }

  // One number for the strip: the slowest collection, since that is the one an
  // operator would act on. The per-collection table below carries the detail.
  const vectorRows = toRows(data.vector_search_p95_seconds)
  const worstVector = vectorRows.length ? vectorRows[0] : null
  const filterReasons = toRows(data.retrieval_filtered_by_reason)

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          title={t('retrieval.title')}
          description={t('retrieval.perTurnDescription')}
        />
        <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat
            label={METRIC_LABELS.hit_rate}
            value={formatPercent(data.hit_rate)}
            hint={t('retrieval.turnsHint', { count: formatCount(data.turns) })}
          />
          <Stat
            label={METRIC_LABELS.empty_retrieval_rate}
            value={formatPercent(data.empty_retrieval_rate)}
            hint={t('retrieval.retrievedNothing')}
            variant={thresholdVariant(data.empty_retrieval_rate, 'empty_retrieval_rate')}
          />
          <Stat
            label={METRIC_LABELS.mean_chunk_count}
            value={formatDecimal(data.mean_chunk_count)}
            hint={t('retrieval.meanPerTurn')}
          />
          <Stat
            label={METRIC_LABELS.vector_search_p95}
            value={promAvailable ? formatSeconds(worstVector?.value) : EMPTY}
            hint={worstVector
              ? t('retrieval.slowest', { name: worstVector.key })
              : t('meta.platformScopeNote')}
          />
        </dl>
      </Card>

      <Card>
        <CardHeader
          title={t('retrieval.filteredOut')}
          description={t('retrieval.filteredOutDescription', { note: t('meta.platformScopeNote') })}
        />
        <PromWidget promAvailable={promAvailable}>
          <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat
              label={METRIC_LABELS.retrieval_filtered_rate}
              value={formatPercent(data.retrieval_filtered_rate)}
              hint={t('retrieval.reachingPolicyGate')}
              variant={thresholdVariant(data.retrieval_filtered_rate, 'retrieval_filtered_rate')}
            />
            {filterReasons.map((row) => (
              <Stat
                key={row.key}
                label={translatedLabelFor(FILTER_REASON_LABEL_KEYS, row.key, t)}
                value={formatDecimal(row.value)}
                hint={t('retrieval.chunksPerSecond')}
              />
            ))}
          </dl>
        </PromWidget>
      </Card>

      <Card>
        <CardHeader
          title={t('retrieval.rerankerEffectiveness')}
          description={t('retrieval.rerankerDescription')}
        />
        <dl className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          <Stat
            label={METRIC_LABELS.reranker_changed_top1_rate}
            value={formatPercent(data.reranker_changed_top1_rate)}
            hint={t('retrieval.ofRerankedTurns', {
              count: formatCount(data.reranker_evaluated_turns),
            })}
          />
          <Stat
            label={METRIC_LABELS.reranker_p95_seconds}
            value={promAvailable ? formatSeconds(data.reranker_p95_seconds) : EMPTY}
            hint={t('retrieval.costOfLift')}
          />
          <Stat
            label={t('retrieval.meanTopScore')}
            value={formatScore(data.mean_top_score)}
            hint={t('retrieval.retrieverScoreRange')}
          />
        </dl>
        <div className="mt-4">
          {/* Scored 0–10 by the reranker model — labelled, because every other
              score on this tab is 0–1 and an unlabelled 7.2 reads as broken. */}
          <PromWidget promAvailable={promAvailable}>
            <Histogram
              label={t('retrieval.rerankerHistogram')}
              accent="var(--info)"
              buckets={toBuckets(data.reranker_top_score_histogram)}
            />
          </PromWidget>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title={t('retrieval.topScoreDistribution')}
            description={t('retrieval.topScoreDescription')}
          />
          <Histogram
            label={t('retrieval.topScoreChart')}
            accent="var(--primary)"
            buckets={toBuckets(data.top_score_histogram)}
          />
        </Card>

        <Card>
          <CardHeader
            title={t('retrieval.chunksPerQuery')}
            description={t('retrieval.chunksPerQueryDescription')}
          />
          <Histogram
            label={t('retrieval.chunksPerQuery')}
            accent="var(--success)"
            buckets={toBuckets(data.chunks_per_query)}
          />
        </Card>
      </div>

      <Card>
        <CardHeader
          title={t('retrieval.scoreGap')}
          description={t('retrieval.scoreGapDescription', {
            measured: formatCount(data.score_gap_turns),
            total: formatCount(data.turns),
          })}
        />
        <dl className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat
            label={METRIC_LABELS.mean_score_gap}
            value={formatScore(data.mean_score_gap)}
            hint={t('retrieval.widerMeansClearer')}
          />
        </dl>
        <Histogram
          label={t('retrieval.scoreGapChart')}
          accent="var(--warning)"
          buckets={toBuckets(data.score_gap_histogram)}
        />
      </Card>

      <Card>
        <CardHeader
          title={t('retrieval.vectorByCollection')}
          description={t('retrieval.vectorDescription', { note: t('meta.platformScopeNote') })}
        />
        <PromWidget promAvailable={promAvailable}>
          {vectorRows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <caption className="sr-only">{t('retrieval.vectorCaption')}</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('retrieval.collection')}</th>
                    <th scope="col" className="py-1.5 pe-3 text-end font-medium">p95</th>
                    <th scope="col" className="py-1.5 text-end font-medium">{t('retrieval.searchesPerSecond')}</th>
                  </tr>
                </thead>
                <tbody>
                  {vectorRows.map((row) => (
                    <tr key={row.key} className="border-t" style={{ borderColor: 'var(--border)' }}>
                      {/* A Qdrant collection name is an identifier. */}
                      <th
                        scope="row"
                        dir="ltr"
                        className="py-1.5 pe-3 text-start font-normal [unicode-bidi:isolate]"
                        style={{ color: 'var(--fg)' }}
                      >
                        {row.key || EMPTY}
                      </th>
                      <td
                        className="py-1.5 pe-3 text-end tabular-nums"
                        style={{ color: 'var(--fg-muted)' }}
                      >
                        {formatSeconds(row.value)}
                      </td>
                      <td className="py-1.5 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                        {formatDecimal(data.vector_search_rate?.[row.key])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              icon={Search}
              size="sm"
              title={t('retrieval.noVectorSearches')}
              description={t('retrieval.noVectorSearchesDescription')}
            />
          )}
        </PromWidget>
      </Card>
    </div>
  )
}
