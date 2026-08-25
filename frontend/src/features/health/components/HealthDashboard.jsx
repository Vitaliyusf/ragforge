'use client'

import { useMemo } from 'react'
import {
  Server, RefreshCw, AlertTriangle, CheckCircle2, XCircle, Gauge, HeartPulse, ShieldCheck,
} from 'lucide-react'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import PageHeader from '@/components/ui/PageHeader'
import StatCard from '@/components/ui/StatCard'
import EmptyState from '@/components/ui/EmptyState'
import ProgressBar from '@/components/ui/ProgressBar'
import { useHealth } from '../hooks/useHealth'

import ServiceCard from './ServiceCard'
import CircuitBreakerPanel from './CircuitBreakerPanel'
import RateLimiterPanel from './RateLimiterPanel'
import MiniSparkline from './MiniSparkline'
import { STATUS_CONFIG, SERVICE_LABELS } from './healthConfig'

export default function HealthDashboard() {
  const { health, loading, error, history, refresh } = useHealth()

  const overallCfg    = STATUS_CONFIG[health?.status] || STATUS_CONFIG.unknown
  const OverallIcon   = overallCfg.icon
  const services      = health?.services || {}
  const serviceList   = Object.entries(services)
  const totalServices = serviceList.length

  const { healthyCount, degradedCount, unhealthyCount } = useMemo(() => ({
    healthyCount:   serviceList.filter(([, s]) => s.status === 'healthy').length,
    degradedCount:  serviceList.filter(([, s]) => s.status === 'degraded').length,
    unhealthyCount: serviceList.filter(([, s]) => s.status === 'unhealthy').length,
  }), [serviceList])
  const healthPercent = totalServices > 0 ? Math.round((healthyCount / totalServices) * 100) : 0

  const healthTimeline = useMemo(() =>
    history.map(h => h.data?.services
      ? Object.values(h.data.services).filter(s => s.status === 'healthy').length
      : 0
    ), [history])

  return (
    <div
      className="mx-auto flex h-full w-full max-w-7xl flex-col gap-5 overflow-y-auto px-3 py-4 md:px-6 md:py-5"
    >
      {/* ── Page header ── */}
      <PageHeader
        title="System health"
        description={health?.timestamp
          ? `Last updated ${new Date(health.timestamp * 1000).toLocaleTimeString()}`
          : 'A live view of service availability and platform protection'}
        icon={HeartPulse}
        badge={
          health && (
            <Badge variant={overallCfg.badgeVariant} dot>
              {overallCfg.label}
            </Badge>
          )
        }
        actions={
          <div className="flex items-center gap-2">
            {healthTimeline.length > 1 && <MiniSparkline data={healthTimeline} />}
            <Button variant="secondary" size="sm" onClick={refresh} disabled={loading}
              leftIcon={<RefreshCw size={13} className={loading ? 'animate-spin' : ''} />}>
              Refresh
            </Button>
          </div>
        }
      />

      {/* ── Error banner ── */}
      {error && (
        <div
          className="flex items-center gap-2.5 px-4 py-3 rounded-xl text-[15px]"
          style={{ background: 'var(--danger-soft)', border: '1px solid rgba(239,68,68,0.25)', color: 'var(--danger)' }}
        >
          <AlertTriangle size={15} />
          {error}
        </div>
      )}

      {/* ── KPI stat row ── */}
      <div
        className="relative overflow-hidden rounded-3xl border p-5 md:p-6"
        style={{ background: 'var(--gradient-subtle)', borderColor: overallCfg.border, boxShadow: 'var(--shadow-md)' }}
      >
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-primary-soft blur-3xl" />
        <div className="relative flex flex-col gap-5 md:flex-row md:items-center">
          <span
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border"
            style={{ background: overallCfg.bg, borderColor: overallCfg.border, color: overallCfg.iconColor }}
          >
            <OverallIcon size={25} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold tracking-tight text-text-primary">
                {health?.status === 'healthy'
                  ? 'All monitored systems are operational'
                  : health?.status === 'degraded'
                    ? 'Some systems are running in a degraded state'
                    : health?.status === 'unhealthy'
                      ? 'Platform intervention is required'
                      : 'Waiting for platform telemetry'}
              </h2>
              <Badge variant={overallCfg.badgeVariant} dot>{overallCfg.label}</Badge>
            </div>
            <p className="mt-1 text-[15px] text-text-muted">
              {healthyCount} of {totalServices} services are responding normally.
            </p>
            <div className="mt-4 flex items-center gap-3">
              <ProgressBar
                value={healthPercent}
                color={overallCfg.iconColor}
                thickness="md"
                className="flex-1"
                aria-label="Service health"
              />
              <span className="text-[13px] font-semibold tabular-nums" style={{ color: overallCfg.iconColor }}>{healthPercent}%</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 md:w-[260px]">
            {[
              ['Healthy', healthyCount, 'var(--success)'],
              ['Degraded', degradedCount, 'var(--warning)'],
              ['Down', unhealthyCount, 'var(--danger)'],
            ].map(([label, value, color]) => (
              <div key={label} className="rounded-xl border border-border bg-bg-elevated/70 px-3 py-2.5 text-center backdrop-blur">
                <div className="text-xl font-semibold tabular-nums" style={{ color }}>{value}</div>
                <div className="mt-0.5 text-xs uppercase tracking-wide text-text-muted">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Monitored" value={totalServices} icon={Server} variant="info" subLabel="registered services" />
        <StatCard label="Healthy"   value={healthyCount}   icon={CheckCircle2} variant="success" subLabel={`of ${totalServices} services`} />
        <StatCard label="Degraded"  value={degradedCount}  icon={AlertTriangle} variant="warning" />
        <StatCard label="Unhealthy" value={unhealthyCount} icon={XCircle}      variant="danger" />
      </div>

      {/* ── Services grid ── */}
      <div
        className="rounded-2xl p-4 shadow-sm md:p-5"
        style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Server size={14} style={{ color: 'var(--fg-soft)' }} />
          <div>
            <span className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>Service map</span>
            <p className="mt-0.5 text-xs text-text-muted">Live status for every platform dependency</p>
          </div>
          <span className="ml-auto text-[13px]" style={{ color: 'var(--fg-soft)' }}>
            {healthyCount}/{totalServices} online
          </span>
        </div>

        {loading && !health ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="h-20 rounded-xl animate-shimmer" />
            ))}
          </div>
        ) : serviceList.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {serviceList.map(([name, info], i) => (
              <ServiceCard key={name} name={name} info={info} index={i} />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Activity}
            title="No service data"
            description="Service health data is not available yet."
            size="sm"
          />
        )}
      </div>

      {/* ── Bottom panels ── */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-2xl p-4 shadow-sm md:p-5" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border)' }}>
          <div className="flex items-center gap-2 mb-4">
            <ShieldCheck size={14} style={{ color: 'var(--fg-soft)' }} />
            <div>
              <span className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>Circuit breakers</span>
              <p className="mt-0.5 text-xs text-text-muted">Failure isolation by dependency</p>
            </div>
          </div>
          <CircuitBreakerPanel breakers={health?.circuit_breakers} />
        </div>

        <div className="rounded-2xl p-4 shadow-sm md:p-5" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border)' }}>
          <div className="flex items-center gap-2 mb-4">
            <Gauge size={14} style={{ color: 'var(--fg-soft)' }} />
            <div>
              <span className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>Rate limiter</span>
              <p className="mt-0.5 text-xs text-text-muted">Traffic admission and rejection</p>
            </div>
          </div>
          <RateLimiterPanel metrics={health?.rate_limiter} />
        </div>
      </div>
    </div>
  )
}
