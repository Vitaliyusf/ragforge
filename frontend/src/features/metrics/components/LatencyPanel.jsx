'use client'

import { AlertTriangle, BarChart3 } from 'lucide-react'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import EmptyState from '@/components/feedback/EmptyState'
import TabSkeleton from '@/components/ui/TabSkeleton'
import Histogram from './charts/Histogram'
import StageBreakdown from './charts/StageBreakdown'
import TimeSeries from './charts/TimeSeries'
import {
  EMPTY,
  PROM_UNAVAILABLE,
  SERVICE_LABELS,
  STAGE_LABELS,
  formatMs,
  formatPercent,
  formatRate,
  formatSeconds,
  labelFor,
} from './metricsConfig'
import { useI18n } from '@/i18n'

const PERCENTILES = ['p50', 'p95', 'p99']

/** Prometheus range results ({t, v}) into TimeSeries points. */
function toPoints(rows) {
  return (rows || [])
    .filter((row) => Number.isFinite(Number(row?.t)) && Number.isFinite(Number(row?.v)))
    .map((row) => [Number(row.t), Number(row.v)])
}

/** Sort a `{label: value}` map into descending rows. */
function toRows(map, labels) {
  return Object.entries(map || {})
    .filter(([, value]) => Number.isFinite(Number(value)))
    .map(([key, value]) => ({ key, label: labelFor(labels, key), value: Number(value) }))
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

function PercentileTable({ title, byPercentile }) {
  const { t } = useI18n()
  const modes = Array.from(
    new Set(PERCENTILES.flatMap((p) => Object.keys(byPercentile?.[p] || {})))
  )
  if (!modes.length) return null
  return (
    <table className="w-full text-[13px]">
      <caption className="sr-only">{title}</caption>
      <thead>
        <tr style={{ color: 'var(--fg-muted)' }}>
          {/* The header is copy and follows the interface direction; the
              percentile names are metric identifiers and stay as written. */}
          <th scope="col" className="py-1.5 text-start font-medium">{t('latency.answerMode')}</th>
          {PERCENTILES.map((p) => (
            <th key={p} scope="col" className="py-1.5 text-end font-medium">{p}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {modes.map((mode) => (
          <tr key={mode} className="border-t" style={{ borderColor: 'var(--border)' }}>
            <th scope="row" className="py-1.5 text-start font-normal" style={{ color: 'var(--fg)' }}>
              {mode || t('latency.defaultMode')}
            </th>
            {PERCENTILES.map((p) => (
              <td key={p} className="py-1.5 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                {formatSeconds(byPercentile?.[p]?.[mode])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function LatencyPanel({ data, loading, error, promAvailable = true, onRetry }) {
  const { t } = useI18n()
  if (loading && !data) return <TabSkeleton />

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title={t('latency.loadFailed')}
        description={error}
        action={onRetry ? <Button onClick={onRetry}>{t('common.retry')}</Button> : undefined}
      />
    )
  }

  if (!data) {
    return (
      <EmptyState
        icon={BarChart3}
        title={t('latency.noData')}
        description={t('latency.noDataDescription')}
      />
    )
  }

  const services = Array.from(
    new Set([
      ...Object.keys(data.http_p95_seconds || {}),
      ...Object.keys(data.http_p99_seconds || {}),
      ...Object.keys(data.http_request_rate || {}),
    ])
  )
  const rpcRows = toRows(data.rpc_roundtrip_p95_seconds, SERVICE_LABELS)
  const stages = toRows(data.stage_p95_seconds, STAGE_LABELS)

  return (
    <div className="flex flex-col gap-4">
      {/* MongoDB-backed. These stay put when Prometheus is down. */}
      <Card>
        <CardHeader
          title={t('latency.recordedTurns')}
          description={t('latency.recordedTurnsDescription')}
        />
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            [t('latency.turns'), data.turns ?? EMPTY],
            [t('latency.meanLatency'), formatMs(data.mean_latency_ms)],
            [t('latency.meanTtft'), formatMs(data.mean_ttft_ms)],
            [t('latency.errorRate'), formatPercent(data.error_rate)],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="label-xs">{label}</dt>
              <dd className="mt-0.5 text-lg font-semibold tabular-nums" style={{ color: 'var(--fg)' }}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card>
        <CardHeader
          title={t('latency.overTime')}
          description={t('latency.overTimeDescription')}
        />
        <PromWidget promAvailable={promAvailable}>
          <TimeSeries
            label={t('latency.overTimeChart')}
            height={200}
            yFormat={formatSeconds}
            series={[
              { name: 'Turn latency p95', points: toPoints(data.series?.turn_latency_p95_series) },
              { name: 'TTFT p95', points: toPoints(data.series?.ttft_p95_series), color: 'var(--info)' },
            ]}
          />
        </PromWidget>
      </Card>

      <Card>
          <CardHeader
            title={t('latency.throughputOverTime')}
            description={t('latency.requestsPerSecond')}
          />
        <PromWidget promAvailable={promAvailable}>
          <TimeSeries
            label={t('latency.throughputChart')}
            height={160}
            yFormat={formatRate}
            series={[
              { name: 'QPS', points: toPoints(data.series?.qps_series), color: 'var(--success)' },
            ]}
          />
        </PromWidget>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title={t('latency.turnPercentiles')}
            description={t('latency.currentByMode')}
          />
          <PromWidget promAvailable={promAvailable}>
            <PercentileTable title={t('latency.turnPercentiles')} byPercentile={data.turn_latency_seconds} />
          </PromWidget>
        </Card>

        <Card>
          <CardHeader
            title={t('latency.ttftPercentiles')}
            description={t('latency.currentByMode')}
          />
          <PromWidget promAvailable={promAvailable}>
            <PercentileTable title={t('latency.ttftPercentiles')} byPercentile={data.ttft_seconds} />
          </PromWidget>
        </Card>
      </div>

      <Card>
        <CardHeader
          title={t('latency.stageBreakdown')}
          description={t('latency.stageBreakdownDescription')}
        />
        <PromWidget promAvailable={promAvailable}>
          <StageBreakdown
            label={t('latency.stageChart')}
            stages={stages}
            valueFormat={formatSeconds}
          />
        </PromWidget>
      </Card>

      <Card>
        <CardHeader
          title={t('latency.byService')}
          description={t('latency.byServiceDescription')}
        />
        <PromWidget promAvailable={promAvailable}>
          {services.length ? (
            <table className="w-full text-[13px]">
              <caption className="sr-only">{t('latency.byServiceCaption')}</caption>
              <thead>
                <tr style={{ color: 'var(--fg-muted)' }}>
                  {/* p95, p99 and RPS are metric identifiers, not copy. */}
                  <th scope="col" className="py-1.5 text-start font-medium">{t('latency.service')}</th>
                  <th scope="col" className="py-1.5 text-end font-medium">p95</th>
                  <th scope="col" className="py-1.5 text-end font-medium">p99</th>
                  <th scope="col" className="py-1.5 text-end font-medium">RPS</th>
                </tr>
              </thead>
              <tbody>
                {services.map((service) => (
                  <tr key={service} className="border-t" style={{ borderColor: 'var(--border)' }}>
                    {/* Service display names are canonical English. */}
                    <th scope="row" dir="ltr" className="py-1.5 text-start font-normal [unicode-bidi:isolate]" style={{ color: 'var(--fg)' }}>
                      {labelFor(SERVICE_LABELS, service)}
                    </th>
                    <td className="py-1.5 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatSeconds(data.http_p95_seconds?.[service])}
                    </td>
                    <td className="py-1.5 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatSeconds(data.http_p99_seconds?.[service])}
                    </td>
                    <td className="py-1.5 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatRate(data.http_request_rate?.[service])}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </PromWidget>
      </Card>

      <Card>
          <CardHeader
            title={t('latency.rpcRoundTrips')}
            description={t('latency.rpcDescription')}
          />
        <PromWidget promAvailable={promAvailable}>
          <Histogram
            label={t('latency.rpcChart')}
            accent="var(--info)"
            valueFormat={formatSeconds}
            showShare={false}
            buckets={rpcRows.map((row) => ({ label: row.label, count: row.value }))}
          />
        </PromWidget>
      </Card>
    </div>
  )
}
