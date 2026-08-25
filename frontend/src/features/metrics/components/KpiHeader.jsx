'use client'

import {
  Activity,
  AlertTriangle,
  DollarSign,
  ShieldCheck,
  ThumbsUp,
  Timer,
  Zap,
} from 'lucide-react'
import StatCard from '@/components/ui/StatCard'
import {
  EMPTY,
  METRIC_LABELS,
  PROM_UNAVAILABLE,
  formatCost,
  formatPercent,
  formatRate,
  formatScore,
  formatSeconds,
  scoreVariant,
  thresholdVariant,
} from './metricsConfig'

/**
 * Reduce a `{answer_mode: value}` map to the worst mode.
 *
 * The API reports these percentiles per answer mode and offers no combined
 * figure. Showing the slowest mode is the honest single number: an average
 * across modes would be a statistic the backend never computed.
 */
function worstByMode(byMode) {
  const entries = Object.entries(byMode || {}).filter(([, value]) => Number.isFinite(Number(value)))
  if (!entries.length) return { value: null, mode: null, modes: 0 }
  const [mode, value] = entries.reduce((best, entry) => (entry[1] > best[1] ? entry : best))
  return { value, mode, modes: entries.length }
}

function modeSubLabel({ mode, modes }) {
  if (!mode) return undefined
  return modes > 1 ? `Slowest mode: ${mode}` : mode
}

/**
 * KPI row for the metrics tab.
 *
 * Prometheus-backed cards degrade to the unavailable note on their own while
 * the MongoDB-backed cards beside them keep their values.
 *
 * The API exposes no previous-window comparison, so no card carries a trend
 * arrow. Add one here the moment the envelope grows a prior-period figure.
 */
export default function KpiHeader({ data, promAvailable = true }) {
  const overview = data || {}
  const latencyP95 = worstByMode(overview.turn_latency_seconds?.p95)
  const ttftP95 = worstByMode(overview.ttft_p95_seconds)
  const unavailable = promAvailable ? undefined : PROM_UNAVAILABLE.title

  const cards = [
    {
      key: 'turn_latency_p95',
      label: METRIC_LABELS.turn_latency_p95,
      prometheus: true,
      value: formatSeconds(latencyP95.value),
      subLabel: modeSubLabel(latencyP95),
      variant: thresholdVariant(latencyP95.value, 'turn_latency_p95_seconds'),
      icon: Timer,
    },
    {
      key: 'ttft_p95',
      label: METRIC_LABELS.ttft_p95,
      prometheus: true,
      value: formatSeconds(ttftP95.value),
      subLabel: modeSubLabel(ttftP95),
      variant: thresholdVariant(ttftP95.value, 'ttft_p95_seconds'),
      icon: Zap,
    },
    {
      key: 'qps',
      label: METRIC_LABELS.qps,
      prometheus: true,
      value: formatRate(overview.qps),
      subLabel: 'requests / sec',
      variant: 'info',
      icon: Activity,
    },
    {
      key: 'error_rate',
      label: METRIC_LABELS.error_rate,
      value: formatPercent(overview.error_rate),
      subLabel: `${overview.errored_turns ?? 0} of ${overview.turns ?? 0} turns`,
      variant: thresholdVariant(overview.error_rate, 'error_rate'),
      icon: AlertTriangle,
    },
    {
      key: 'mean_groundedness',
      label: METRIC_LABELS.mean_groundedness,
      value: formatScore(overview.mean_groundedness),
      subLabel: 'judge score, 0–1',
      variant: scoreVariant(overview.mean_groundedness),
      icon: ShieldCheck,
    },
    {
      key: 'thumbs_up_rate',
      label: METRIC_LABELS.thumbs_up_rate,
      value: formatPercent(overview.thumbs_up_rate),
      subLabel: `${overview.thumbs_up ?? 0} up · ${overview.thumbs_down ?? 0} down`,
      variant: 'default',
      icon: ThumbsUp,
    },
    {
      key: 'estimated_cost_usd',
      label: METRIC_LABELS.estimated_cost_usd,
      value: formatCost(overview.cost?.estimated_cost_usd),
      // A $0.00 total next to unpriced models means "nothing here is priced",
      // not "this was free" — so say which it is.
      subLabel: overview.cost?.models_without_pricing?.length
        ? `${overview.cost.models_without_pricing.length} model(s) unpriced`
        : `${overview.cost?.tokens_in ?? 0} in · ${overview.cost?.tokens_out ?? 0} out`,
      variant: 'default',
      icon: DollarSign,
    },
  ]

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-7">
      {cards.map((card) => {
        const blocked = card.prometheus && !promAvailable
        return (
          <StatCard
            key={card.key}
            label={card.label}
            value={blocked ? EMPTY : card.value}
            subLabel={blocked ? unavailable : card.subLabel}
            variant={blocked ? 'default' : card.variant}
            icon={card.icon}
          />
        )
      })}
    </div>
  )
}
