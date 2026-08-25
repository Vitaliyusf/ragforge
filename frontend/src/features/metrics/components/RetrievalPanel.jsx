'use client'

import { AlertTriangle, Search } from 'lucide-react'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import EmptyState from '@/components/ui/EmptyState'
import TabSkeleton from '@/components/ui/TabSkeleton'
import Histogram from './charts/Histogram'
import {
  EMPTY,
  FILTER_REASON_LABELS,
  METRIC_LABELS,
  PLATFORM_SCOPE_NOTE,
  PROM_UNAVAILABLE,
  formatCount,
  formatDecimal,
  formatPercent,
  formatScore,
  formatSeconds,
  labelFor,
  thresholdVariant,
} from './metricsConfig'

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
  if (promAvailable) return children
  return (
    <EmptyState
      icon={AlertTriangle}
      size="sm"
      title={PROM_UNAVAILABLE.title}
      description={PROM_UNAVAILABLE.description}
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
  if (loading && !data) return <TabSkeleton />

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Could not load retrieval metrics"
        description={error}
        action={onRetry ? <Button onClick={onRetry}>Retry</Button> : undefined}
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
        title="No retrieval activity"
        description="No turns in this window reached retrieval."
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
          title="Retrieval"
          description="Per-turn facts from the metrics store, scoped to this tenant."
        />
        <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat
            label={METRIC_LABELS.hit_rate}
            value={formatPercent(data.hit_rate)}
            hint={`${formatCount(data.turns)} turns`}
          />
          <Stat
            label={METRIC_LABELS.empty_retrieval_rate}
            value={formatPercent(data.empty_retrieval_rate)}
            hint="turns that retrieved nothing"
            variant={thresholdVariant(data.empty_retrieval_rate, 'empty_retrieval_rate')}
          />
          <Stat
            label={METRIC_LABELS.mean_chunk_count}
            value={formatDecimal(data.mean_chunk_count)}
            hint="mean per turn"
          />
          <Stat
            label={METRIC_LABELS.vector_search_p95}
            value={promAvailable ? formatSeconds(worstVector?.value) : EMPTY}
            hint={worstVector ? `slowest: ${worstVector.key}` : PLATFORM_SCOPE_NOTE}
          />
        </dl>
      </Card>

      <Card>
        <CardHeader
          title="Filtered out before ranking"
          description={`Chunks withheld by retrieval policy. ${PLATFORM_SCOPE_NOTE}`}
        />
        <PromWidget promAvailable={promAvailable}>
          <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat
              label={METRIC_LABELS.retrieval_filtered_rate}
              value={formatPercent(data.retrieval_filtered_rate)}
              hint="of chunks reaching the policy gate"
              variant={thresholdVariant(data.retrieval_filtered_rate, 'retrieval_filtered_rate')}
            />
            {filterReasons.map((row) => (
              <Stat
                key={row.key}
                label={labelFor(FILTER_REASON_LABELS, row.key)}
                value={formatDecimal(row.value)}
                hint="chunks/sec"
              />
            ))}
          </dl>
        </PromWidget>
      </Card>

      <Card>
        <CardHeader
          title="Reranker effectiveness"
          description="Is the reranker earning its latency? Lift is how often it changed which chunk ranked first."
        />
        <dl className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          <Stat
            label={METRIC_LABELS.reranker_changed_top1_rate}
            value={formatPercent(data.reranker_changed_top1_rate)}
            hint={`of ${formatCount(data.reranker_evaluated_turns)} reranked turns`}
          />
          <Stat
            label={METRIC_LABELS.reranker_p95_seconds}
            value={promAvailable ? formatSeconds(data.reranker_p95_seconds) : EMPTY}
            hint="cost of that lift"
          />
          <Stat
            label="Mean top score"
            value={formatScore(data.mean_top_score)}
            hint="retriever score, 0–1"
          />
        </dl>
        <div className="mt-4">
          {/* Scored 0–10 by the reranker model — labelled, because every other
              score on this tab is 0–1 and an unlabelled 7.2 reads as broken. */}
          <PromWidget promAvailable={promAvailable}>
            <Histogram
              label="Reranker top score per query, 0–10"
              accent="var(--info)"
              buckets={toBuckets(data.reranker_top_score_histogram)}
            />
          </PromWidget>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Top-1 score distribution" description="Best chunk score per turn, 0–1." />
          <Histogram
            label="Top chunk score per turn"
            accent="var(--primary)"
            buckets={toBuckets(data.top_score_histogram)}
          />
        </Card>

        <Card>
          <CardHeader
            title="Chunks returned per query"
            description="How many chunks each turn retrieved."
          />
          <Histogram
            label="Chunks returned per query"
            accent="var(--success)"
            buckets={toBuckets(data.chunks_per_query)}
          />
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Score gap"
          description={`Top score minus the fifth, as a proxy for how discriminative retrieval was. ${formatCount(
            data.score_gap_turns
          )} of ${formatCount(data.turns)} turns returned enough chunks to measure a gap.`}
        />
        <dl className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat
            label={METRIC_LABELS.mean_score_gap}
            value={formatScore(data.mean_score_gap)}
            hint="wider means one clearly best chunk"
          />
        </dl>
        <Histogram
          label="Distribution of the gap between the top and fifth chunk scores"
          accent="var(--warning)"
          buckets={toBuckets(data.score_gap_histogram)}
        />
      </Card>

      <Card>
        <CardHeader
          title="Vector search by collection"
          description={`Search latency p95. ${PLATFORM_SCOPE_NOTE}`}
        />
        <PromWidget promAvailable={promAvailable}>
          {vectorRows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <caption className="sr-only">Vector search p95 latency by collection</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">Collection</th>
                    <th scope="col" className="py-1.5 pr-3 text-right font-medium">p95</th>
                    <th scope="col" className="py-1.5 text-right font-medium">Searches/sec</th>
                  </tr>
                </thead>
                <tbody>
                  {vectorRows.map((row) => (
                    <tr key={row.key} className="border-t" style={{ borderColor: 'var(--border)' }}>
                      <th
                        scope="row"
                        className="py-1.5 pr-3 text-left font-normal"
                        style={{ color: 'var(--fg)' }}
                      >
                        {row.key || EMPTY}
                      </th>
                      <td
                        className="py-1.5 pr-3 text-right tabular-nums"
                        style={{ color: 'var(--fg-muted)' }}
                      >
                        {formatSeconds(row.value)}
                      </td>
                      <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
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
              title="No vector searches"
              description="Prometheus recorded no vector search activity in this window."
            />
          )}
        </PromWidget>
      </Card>
    </div>
  )
}
