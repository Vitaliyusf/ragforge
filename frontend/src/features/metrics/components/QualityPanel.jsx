'use client'

import { AlertTriangle, ShieldCheck } from 'lucide-react'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import EmptyState from '@/components/feedback/EmptyState'
import TabSkeleton from '@/components/ui/TabSkeleton'
import StatCard from '@/components/ui/StatCard'
import DeepLink from '@/components/observability/DeepLink'
import { conversationLink } from '@/lib/observability/deepLinks'
import Histogram from './charts/Histogram'
import {
  CITATION_DENOMINATOR_NOTE,
  CONFIDENCE_LABELS,
  EMPTY,
  HALLUCINATION_VERDICT_LABELS,
  HALLUCINATION_VERDICT_VARIANTS,
  METRIC_LABELS,
  MIXED_HALLUCINATION_NOTE,
  formatCount,
  formatDecimal,
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
 * Two hallucination measures can appear here at once. The claim-level rate
 * is the real one; the groundedness proxy covers turns recorded before
 * claim-level judging existed. They divide by different populations, so when
 * a window contains both kinds of turn the panel shows both and says so.
 * Averaging them into a single figure would describe neither.
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
  const judged = data.hallucination_verdict_turns ?? 0
  const withoutVerdict = data.turns_without_verdict ?? 0
  // Both kinds of turn in one window: the real rate cannot describe the old
  // ones, and the proxy is the only thing that can.
  const mixedWindow = judged > 0 && withoutVerdict > 0
  const showProxy = judged === 0 || mixedWindow

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
            label={METRIC_LABELS.hallucination_rate}
            value={formatPercent(data.hallucination_rate)}
            hint={`Claim-level, over ${formatCount(judged)} judged ${
              judged === 1 ? 'turn' : 'turns'
            }`}
            variant={thresholdVariant(data.hallucination_rate, 'hallucination_rate')}
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

      <Card>
        <CardHeader
          title="Hallucination"
          description="From the judge's claim analysis: how much of each answer the retrieved context did not support."
        />
        {mixedWindow && (
          <p className="mb-3 text-[12px]" style={{ color: 'var(--warning)' }}>
            {MIXED_HALLUCINATION_NOTE}
          </p>
        )}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label={METRIC_LABELS.hallucination_rate}
            value={formatPercent(data.hallucination_rate)}
            subLabel={`${formatCount(judged)} judged, ${formatCount(
              withoutVerdict
            )} without a verdict`}
            variant={thresholdVariant(data.hallucination_rate, 'hallucination_rate')}
          />
          <StatCard
            label={METRIC_LABELS.hallucination_severe_rate}
            value={formatPercent(data.hallucination_severe_rate)}
            subLabel="answers a reader could act on wrongly"
          />
          <StatCard
            label={METRIC_LABELS.mean_unsupported_claims}
            value={formatDecimal(data.mean_unsupported_claims)}
            subLabel={`over ${formatCount(data.unsupported_claim_turns)} answers`}
          />
          {showProxy && (
            <StatCard
              label={METRIC_LABELS.hallucination_rate_proxy_groundedness}
              value={formatPercent(data.hallucination_rate_proxy_groundedness)}
              // The older measure, shown only when it is the only thing that
              // can describe part of the window. Never merged into the rate
              // beside it: a threshold over one score is a different claim.
              subLabel={
                threshold != null
                  ? `groundedness below ${formatScore(threshold)}, over ${formatCount(
                      data.scored_turns
                    )} scored turns`
                  : 'threshold over the judge groundedness score'
              }
            />
          )}
        </div>
        <div className="mt-4">
          <Histogram
            label="Answers by hallucination verdict"
            accent="var(--danger)"
            buckets={(data.hallucination_verdict_mix || []).map((row) => ({
              label: labelFor(HALLUCINATION_VERDICT_LABELS, row?.verdict),
              count: Number(row?.count) || 0,
            }))}
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Citations"
          description="Whether answers cite the passages that support them, and whether those citations hold up."
        />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label={METRIC_LABELS.mean_citation_precision}
            value={formatPercent(data.mean_citation_precision)}
            // The excluded count travels with the mean: a precision of 100%
            // over two answers is not the same claim as one over two hundred.
            subLabel={`over ${formatCount(data.citation_precision_turns)} answers · ${formatCount(
              data.citation_precision_excluded
            )} had no citations`}
            variant={scoreVariant(data.mean_citation_precision)}
          />
          <StatCard
            label={METRIC_LABELS.mean_citation_recall}
            value={formatPercent(data.mean_citation_recall)}
            subLabel={`over ${formatCount(data.citation_recall_turns)} answers · ${formatCount(
              data.citation_recall_excluded
            )} had no supportable claims`}
            variant={scoreVariant(data.mean_citation_recall)}
          />
          <StatCard
            label={METRIC_LABELS.citation_f1}
            value={formatPercent(data.citation_f1)}
            subLabel="harmonic mean of the two means"
          />
          <StatCard
            label={METRIC_LABELS.mean_citation_count}
            value={formatDecimal(data.mean_citation_count)}
            subLabel={`${formatCount(data.answers_with_citations)} answers cited a source`}
          />
        </div>
        <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {CITATION_DENOMINATOR_NOTE}
        </p>
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
          description="Lowest groundedness in this window, worst first. Identifiers, scores and claim counts only — no conversation or claim text."
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
                  <th scope="col" className="py-1.5 pr-3 text-right font-medium">Unsupported claims</th>
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">Hallucination</th>
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">Confidence</th>
                  <th scope="col" className="py-1.5 text-left font-medium">
                    <span className="sr-only">Open the conversation</span>
                  </th>
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
                    <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {turn.unsupported_claim_count == null
                        ? EMPTY
                        : formatCount(turn.unsupported_claim_count)}
                    </td>
                    <td
                      className="py-1.5 pr-3"
                      style={{
                        color:
                          VARIANT_COLORS[
                            HALLUCINATION_VERDICT_VARIANTS[turn.hallucination_verdict]
                          ] || 'var(--fg-muted)',
                      }}
                    >
                      {turn.hallucination_verdict
                        ? labelFor(HALLUCINATION_VERDICT_LABELS, turn.hallucination_verdict)
                        : EMPTY}
                    </td>
                    <td className="py-1.5 pr-3" style={{ color: 'var(--fg-muted)' }}>
                      {labelFor(CONFIDENCE_LABELS, turn.confidence)}
                    </td>
                    {/* The metrics store records the same conversation id the
                        chat route is keyed by, so a low score is one click
                        from the exchange that produced it. */}
                    <td className="py-1.5">
                      <DeepLink link={conversationLink(turn.conversation_id)} />
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
