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
  CONFIDENCE_LABEL_KEYS,
  EMPTY,
  HALLUCINATION_VERDICT_LABEL_KEYS,
  HALLUCINATION_VERDICT_VARIANTS,
  METRIC_LABELS,
  formatCount,
  formatDecimal,
  formatPercent,
  formatScore,
  labelFor,
  translatedLabelFor,
  scoreVariant,
  thresholdVariant,
} from './metricsConfig'
import { intlLocale } from '@/lib/formatting/datetime'
import { useI18n } from '@/i18n'

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
  const { locale, t } = useI18n()
  if (loading && !data) return <TabSkeleton />

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title={t('quality.loadFailed')}
        description={error}
        action={onRetry ? <Button onClick={onRetry}>{t('common.retry')}</Button> : undefined}
      />
    )
  }

  if (!data) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title={t('quality.noData')}
        description={t('quality.noDataDescription')}
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
          title={t('quality.rates')}
          description={t('quality.ratesDescription', {
            scored: data.scored_turns ?? 0,
            total: data.turns ?? 0,
          })}
        />
        <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Rate
            label={METRIC_LABELS.mean_groundedness}
            value={formatScore(data.mean_groundedness)}
            hint={t('quality.judgeScoreRange')}
            variant={scoreVariant(data.mean_groundedness)}
          />
          <Rate
            label={METRIC_LABELS.hallucination_rate}
            value={formatPercent(data.hallucination_rate)}
            hint={t('quality.claimLevelOver', { count: formatCount(judged) })}
            variant={thresholdVariant(data.hallucination_rate, 'hallucination_rate')}
          />
          <Rate
            label={METRIC_LABELS.revision_rate}
            value={formatPercent(data.revision_rate)}
            hint={t('quality.evaluatedForRevision')}
          />
          <Rate
            label={METRIC_LABELS.guardrail_block_rate}
            value={formatPercent(data.guardrail_block_rate)}
            hint={t('quality.reachedGuardrail')}
            variant={thresholdVariant(data.guardrail_block_rate, 'guardrail_block_rate')}
          />
        </dl>
      </Card>

      <Card>
        <CardHeader
          title={t('quality.hallucination')}
          description={t('quality.hallucinationDescription')}
        />
        {mixedWindow && (
          <p className="mb-3 text-[12px]" style={{ color: 'var(--warning)' }}>
            {t('quality.mixedHallucinationNote')}
          </p>
        )}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label={METRIC_LABELS.hallucination_rate}
            value={formatPercent(data.hallucination_rate)}
            subLabel={t('quality.judgedWithoutVerdict', {
              judged: formatCount(judged),
              without: formatCount(withoutVerdict),
            })}
            variant={thresholdVariant(data.hallucination_rate, 'hallucination_rate')}
          />
          <StatCard
            label={METRIC_LABELS.hallucination_severe_rate}
            value={formatPercent(data.hallucination_severe_rate)}
            subLabel={t('quality.actOnWrongly')}
          />
          <StatCard
            label={METRIC_LABELS.mean_unsupported_claims}
            value={formatDecimal(data.mean_unsupported_claims)}
            subLabel={t('quality.overAnswers', {
              count: formatCount(data.unsupported_claim_turns),
            })}
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
                  ? t('quality.proxyThreshold', {
                      threshold: formatScore(threshold),
                      count: formatCount(data.scored_turns),
                    })
                  : t('quality.proxyGeneric')
              }
            />
          )}
        </div>
        <div className="mt-4">
          <Histogram
            label={t('quality.verdictChart')}
            accent="var(--danger)"
            buckets={(data.hallucination_verdict_mix || []).map((row) => ({
              label: translatedLabelFor(HALLUCINATION_VERDICT_LABEL_KEYS, row?.verdict, t),
              count: Number(row?.count) || 0,
            }))}
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title={t('quality.citations')}
          description={t('quality.citationsDescription')}
        />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label={METRIC_LABELS.mean_citation_precision}
            value={formatPercent(data.mean_citation_precision)}
            // The excluded count travels with the mean: a precision of 100%
            // over two answers is not the same claim as one over two hundred.
            subLabel={t('quality.precisionSubLabel', {
              count: formatCount(data.citation_precision_turns),
              excluded: formatCount(data.citation_precision_excluded),
            })}
            variant={scoreVariant(data.mean_citation_precision)}
          />
          <StatCard
            label={METRIC_LABELS.mean_citation_recall}
            value={formatPercent(data.mean_citation_recall)}
            subLabel={t('quality.recallSubLabel', {
              count: formatCount(data.citation_recall_turns),
              excluded: formatCount(data.citation_recall_excluded),
            })}
            variant={scoreVariant(data.mean_citation_recall)}
          />
          <StatCard
            label={METRIC_LABELS.citation_f1}
            value={formatPercent(data.citation_f1)}
            subLabel={t('quality.harmonicMean')}
          />
          <StatCard
            label={METRIC_LABELS.mean_citation_count}
            value={formatDecimal(data.mean_citation_count)}
            subLabel={t('quality.citedASource', {
              count: formatCount(data.answers_with_citations),
            })}
          />
        </div>
        <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {t('quality.citationDenominatorNote')}
        </p>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {[
          ['eval.groundedness', data.groundedness_histogram, 'var(--primary)'],
          ['eval.completeness', data.completeness_histogram, 'var(--info)'],
          ['eval.safety', data.safety_histogram, 'var(--success)'],
        ].map(([titleKey, rows, accent]) => (
          <Card key={titleKey}>
            <CardHeader title={t(titleKey)} description={t('quality.scoreDistribution')} />
            <Histogram
              label={t('quality.scoreDistributionChart', { name: t(titleKey) })}
              accent={accent}
              buckets={toBuckets(rows)}
            />
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader
          title={t('quality.confidenceMix')}
          description={t('quality.confidenceMixDescription')}
        />
        <Histogram
          label={t('quality.confidenceChart')}
          accent="var(--warning)"
          buckets={(data.confidence_mix || []).map((row) => ({
            label: translatedLabelFor(CONFIDENCE_LABEL_KEYS, row?.level, t),
            count: Number(row?.count) || 0,
          }))}
        />
      </Card>

      <Card>
        <CardHeader
          title={t('quality.worstTurns')}
          description={t('quality.worstTurnsDescription')}
        />
        {worstTurns.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <caption className="sr-only">{t('quality.worstTurnsCaption')}</caption>
              <thead>
                <tr style={{ color: 'var(--fg-muted)' }}>
                  <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('quality.turn')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('quality.recorded')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-end font-medium">{t('eval.groundedness')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-end font-medium">{t('eval.completeness')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-end font-medium">{t('eval.safety')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-end font-medium">{t('quality.unsupportedClaims')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('quality.hallucination')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('quality.confidence')}</th>
                  <th scope="col" className="py-1.5 text-start font-medium">
                    <span className="sr-only">{t('quality.openConversation')}</span>
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
                    {/* A turn id is an identifier an operator may copy. */}
                    <th
                      scope="row"
                      dir="ltr"
                      className="max-w-[16rem] truncate py-1.5 pe-3 text-start font-mono text-[12px] font-normal [unicode-bidi:isolate]"
                      style={{ color: 'var(--fg)' }}
                      title={turn.turn_id}
                    >
                      {turn.turn_id || EMPTY}
                    </th>
                    <td className="py-1.5 pe-3" style={{ color: 'var(--fg-muted)' }}>
                      {turn.ts ? new Date(turn.ts).toLocaleString(intlLocale(locale)) : EMPTY}
                    </td>
                    <td
                      className="py-1.5 pe-3 text-end tabular-nums font-medium"
                      style={{ color: VARIANT_COLORS[scoreVariant(turn.groundedness)] }}
                    >
                      {formatScore(turn.groundedness)}
                    </td>
                    <td className="py-1.5 pe-3 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatScore(turn.completeness)}
                    </td>
                    <td className="py-1.5 pe-3 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatScore(turn.safety)}
                    </td>
                    <td className="py-1.5 pe-3 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {turn.unsupported_claim_count == null
                        ? EMPTY
                        : formatCount(turn.unsupported_claim_count)}
                    </td>
                    <td
                      className="py-1.5 pe-3"
                      style={{
                        color:
                          VARIANT_COLORS[
                            HALLUCINATION_VERDICT_VARIANTS[turn.hallucination_verdict]
                          ] || 'var(--fg-muted)',
                      }}
                    >
                      {turn.hallucination_verdict
                        ? translatedLabelFor(HALLUCINATION_VERDICT_LABEL_KEYS, turn.hallucination_verdict, t)
                        : EMPTY}
                    </td>
                    <td className="py-1.5 pe-3" style={{ color: 'var(--fg-muted)' }}>
                      {translatedLabelFor(CONFIDENCE_LABEL_KEYS, turn.confidence, t)}
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
            title={t('quality.noScoredTurns')}
            description={t('quality.noScoredTurnsDescription')}
          />
        )}
      </Card>
    </div>
  )
}
