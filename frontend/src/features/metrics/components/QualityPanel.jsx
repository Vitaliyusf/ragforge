'use client'

import { AlertTriangle, ShieldCheck } from 'lucide-react'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import EmptyState from '@/components/ui/EmptyState'
import TabSkeleton from '@/components/ui/TabSkeleton'
import Histogram from './charts/Histogram'
import {
  CONFIDENCE_LABELS,
  EMPTY,
  METRIC_LABELS,
  formatPercent,
  formatScore,
  labelFor,
  scoreVariant,
  thresholdVariant,
} from './metricsConfig'

const VARIANT_COLORS = {
  default: 'var(--fg)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
}

/** `{bucket, count}` from the aggregation into the chart's `{label, count}`. */
function toBuckets(rows) {
  return (rows || []).map((row) => ({ label: String(row?.bucket ?? ''), count: Number(row?.count) || 0 }))
}

function Rate({ label, value, hint, variant = 'default' }) {
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
 * Answer-quality panel.
 *
 * Every figure here comes from the per-turn facts in MongoDB, so none of it
 * is gated on `prometheus_available` — the quality route sets that flag from
 * a health check alone and no widget on this panel reads Prometheus.
 *
 * There is no citation-coverage widget: the app emits no citations yet, so
 * those fields are always null. Phase 6 adds them.
 *
 * Feedback is not shown here either. Thumbs-up counts live on the overview
 * section, not this one, and fetching a second endpoint for one number would
 * break the one-section-one-request rule. The rate appears in the KPI row.
 */
export default function QualityPanel({ data, loading, error, onRetry }) {
  if (loading && !data) return <TabSkeleton />

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Could not load quality metrics"
        description={error}
        action={onRetry ? <Button onClick={onRetry}>Retry</Button> : undefined}
      />
    )
  }

  if (!data) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="No quality data"
        description="No judged turns were recorded in this window."
      />
    )
  }

  const threshold = data.hallucination_groundedness_threshold
  const worstTurns = data.worst_turns || []

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          title="Quality rates"
          description={`${data.scored_turns ?? 0} of ${data.turns ?? 0} turns carried a judge score.`}
        />
        <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Rate
            label={METRIC_LABELS.mean_groundedness}
            value={formatScore(data.mean_groundedness)}
            hint="judge score, 0–1"
            variant={scoreVariant(data.mean_groundedness)}
          />
          <Rate
            label={METRIC_LABELS.hallucination_rate_proxy_groundedness}
            value={formatPercent(data.hallucination_rate_proxy_groundedness)}
            // Named as a proxy on purpose: this is the share of scored turns
            // falling under a groundedness threshold, not a claim-level
            // measurement. Phase 6 replaces it with a real one.
            hint={
              threshold != null
                ? `Share of scored turns with groundedness below ${formatScore(threshold)}`
                : 'Threshold over the judge groundedness score'
            }
            variant={thresholdVariant(
              data.hallucination_rate_proxy_groundedness,
              'hallucination_rate'
            )}
          />
          <Rate
            label={METRIC_LABELS.revision_rate}
            value={formatPercent(data.revision_rate)}
            hint="of turns that were evaluated for revision"
          />
          <Rate
            label={METRIC_LABELS.guardrail_block_rate}
            value={formatPercent(data.guardrail_block_rate)}
            hint="of turns that reached a guardrail"
            variant={thresholdVariant(data.guardrail_block_rate, 'guardrail_block_rate')}
          />
        </dl>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {[
          ['Groundedness', data.groundedness_histogram, 'var(--primary)'],
          ['Completeness', data.completeness_histogram, 'var(--info)'],
          ['Safety', data.safety_histogram, 'var(--success)'],
        ].map(([title, rows, accent]) => (
          <Card key={title}>
            <CardHeader title={title} description="Score distribution, 0–1." />
            <Histogram
              label={`${title} score distribution`}
              accent={accent}
              buckets={toBuckets(rows)}
            />
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader title="Confidence mix" description="Self-reported confidence per turn." />
        <Histogram
          label="Turns by reported confidence level"
          accent="var(--warning)"
          buckets={(data.confidence_mix || []).map((row) => ({
            label: labelFor(CONFIDENCE_LABELS, row?.level),
            count: Number(row?.count) || 0,
          }))}
        />
      </Card>

      <Card>
        <CardHeader
          title="Worst turns"
          description="Lowest groundedness in this window. Identifiers and scores only — no conversation text."
        />
        {worstTurns.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <caption className="sr-only">Turns with the lowest groundedness scores</caption>
              <thead>
                <tr style={{ color: 'var(--fg-muted)' }}>
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">Turn</th>
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">Recorded</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-medium">Groundedness</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-medium">Completeness</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-medium">Safety</th>
                  <th scope="col" className="py-1.5 text-left font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {worstTurns.map((turn) => (
                  <tr
                    key={turn.turn_id || `${turn.conversation_id}-${turn.ts}`}
                    className="border-t"
                    style={{ borderColor: 'var(--border)' }}
                  >
                    <th
                      scope="row"
                      className="max-w-[16rem] truncate py-1.5 pr-3 text-left font-mono text-[12px] font-normal"
                      style={{ color: 'var(--fg)' }}
                      title={turn.turn_id}
                    >
                      {turn.turn_id || EMPTY}
                    </th>
                    <td className="py-1.5 pr-3" style={{ color: 'var(--fg-muted)' }}>
                      {turn.ts ? new Date(turn.ts).toLocaleString() : EMPTY}
                    </td>
                    <td
                      className="py-1.5 pr-3 text-right tabular-nums font-medium"
                      style={{ color: VARIANT_COLORS[scoreVariant(turn.groundedness)] }}
                    >
                      {formatScore(turn.groundedness)}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatScore(turn.completeness)}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatScore(turn.safety)}
                    </td>
                    <td className="py-1.5" style={{ color: 'var(--fg-muted)' }}>
                      {labelFor(CONFIDENCE_LABELS, turn.confidence)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={ShieldCheck}
            size="sm"
            title="No scored turns"
            description="Nothing in this window carried a groundedness score."
          />
        )}
      </Card>
    </div>
  )
}
