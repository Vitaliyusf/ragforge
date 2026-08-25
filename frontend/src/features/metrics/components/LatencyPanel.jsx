'use client'

import { AlertTriangle, BarChart3 } from 'lucide-react'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import EmptyState from '@/components/ui/EmptyState'
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

function PercentileTable({ title, byPercentile }) {
  const modes = Array.from(
    new Set(PERCENTILES.flatMap((p) => Object.keys(byPercentile?.[p] || {})))
  )
  if (!modes.length) return null
  return (
    <table className="w-full text-[13px]">
      <caption className="sr-only">{title}</caption>
      <thead>
        <tr style={{ color: 'var(--fg-muted)' }}>
          <th scope="col" className="py-1.5 text-left font-medium">Answer mode</th>
          {PERCENTILES.map((p) => (
            <th key={p} scope="col" className="py-1.5 text-right font-medium">{p}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {modes.map((mode) => (
          <tr key={mode} className="border-t" style={{ borderColor: 'var(--border)' }}>
            <th scope="row" className="py-1.5 text-left font-normal" style={{ color: 'var(--fg)' }}>
              {mode || 'default'}
            </th>
            {PERCENTILES.map((p) => (
              <td key={p} className="py-1.5 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
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
  if (loading && !data) return <TabSkeleton />

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Could not load latency metrics"
        description={error}
        action={onRetry ? <Button onClick={onRetry}>Retry</Button> : undefined}
      />
    )
  }

  if (!data) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No latency data"
        description="No turns were recorded in this window."
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
          title="Recorded turns"
          description="Per-turn facts from the metrics store, scoped to this tenant."
        />
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            ['Turns', data.turns ?? EMPTY],
            ['Mean latency', formatMs(data.mean_latency_ms)],
            ['Mean TTFT', formatMs(data.mean_ttft_ms)],
            ['Error rate', formatPercent(data.error_rate)],
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
          title="Latency over time"
          description="Turn latency and time-to-first-token, p95. The API publishes a range series for p95 only; p50 and p99 are shown as current values below."
        />
        <PromWidget promAvailable={promAvailable}>
          <TimeSeries
            label="Turn latency and TTFT, p95, over the window"
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
        <CardHeader title="Throughput over time" description="Requests per second." />
        <PromWidget promAvailable={promAvailable}>
          <TimeSeries
            label="Requests per second over the window"
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
          <CardHeader title="Turn latency percentiles" description="Current values by answer mode." />
          <PromWidget promAvailable={promAvailable}>
            <PercentileTable title="Turn latency percentiles" byPercentile={data.turn_latency_seconds} />
          </PromWidget>
        </Card>

        <Card>
          <CardHeader title="TTFT percentiles" description="Current values by answer mode." />
          <PromWidget promAvailable={promAvailable}>
            <PercentileTable title="TTFT percentiles" byPercentile={data.ttft_seconds} />
          </PromWidget>
        </Card>
      </div>

      <Card>
        <CardHeader title="Where a turn's time goes" description="p95 per stage." />
        <PromWidget promAvailable={promAvailable}>
          <StageBreakdown
            label="Stage p95 breakdown"
            stages={stages}
            valueFormat={formatSeconds}
          />
        </PromWidget>
      </Card>

      <Card>
        <CardHeader
          title="By service"
          description="HTTP percentiles and request rate. The API exposes no per-service error rate, so that column is omitted rather than approximated."
        />
        <PromWidget promAvailable={promAvailable}>
          {services.length ? (
            <table className="w-full text-[13px]">
              <caption className="sr-only">HTTP latency and request rate per service</caption>
              <thead>
                <tr style={{ color: 'var(--fg-muted)' }}>
                  <th scope="col" className="py-1.5 text-left font-medium">Service</th>
                  <th scope="col" className="py-1.5 text-right font-medium">p95</th>
                  <th scope="col" className="py-1.5 text-right font-medium">p99</th>
                  <th scope="col" className="py-1.5 text-right font-medium">RPS</th>
                </tr>
              </thead>
              <tbody>
                {services.map((service) => (
                  <tr key={service} className="border-t" style={{ borderColor: 'var(--border)' }}>
                    <th scope="row" className="py-1.5 text-left font-normal" style={{ color: 'var(--fg)' }}>
                      {labelFor(SERVICE_LABELS, service)}
                    </th>
                    <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatSeconds(data.http_p95_seconds?.[service])}
                    </td>
                    <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatSeconds(data.http_p99_seconds?.[service])}
                    </td>
                    <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
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
        <CardHeader title="RPC round-trips" description="p95 by downstream service." />
        <PromWidget promAvailable={promAvailable}>
          <Histogram
            label="RPC round-trip p95 by downstream"
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
