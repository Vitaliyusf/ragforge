'use client'

import { useMemo } from 'react'
import {
  Activity, Server, ShieldCheck, ShieldOff, RefreshCw,
  CircleDot, AlertTriangle, CheckCircle2, XCircle,
  Zap, Clock, Gauge, HeartPulse,
} from 'lucide-react'
import { motion } from 'framer-motion'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import PageHeader from '@/components/ui/PageHeader'
import StatCard from '@/components/ui/StatCard'
import EmptyState from '@/components/ui/EmptyState'
import ProgressBar from '@/components/ui/ProgressBar'
import { useHealth } from '../hooks/useHealth'

/* ── Status config ──────────────────────────────────────── */
const STATUS_CONFIG = {
  healthy:   { iconColor: 'var(--success)', bg: 'var(--success-soft)', border: 'rgba(34,197,94,0.25)',  icon: CheckCircle2,  label: 'Healthy',   badgeVariant: 'success'  },
  degraded:  { iconColor: 'var(--warning)', bg: 'var(--warning-soft)', border: 'rgba(245,158,11,0.25)', icon: AlertTriangle, label: 'Degraded',  badgeVariant: 'warning'  },
  unhealthy: { iconColor: 'var(--danger)',  bg: 'var(--danger-soft)',  border: 'rgba(239,68,68,0.25)',  icon: XCircle,       label: 'Unhealthy', badgeVariant: 'danger'   },
  unknown:   { iconColor: 'var(--fg-soft)', bg: 'var(--surface-hover)',border: 'var(--border)',          icon: CircleDot,     label: 'Unknown',   badgeVariant: 'default'  },
}

const CB_STATE = {
  closed:    { label: 'Closed',    variant: 'success' },
  open:      { label: 'Open',      variant: 'danger'  },
  half_open: { label: 'Half-Open', variant: 'warning' },
}

const SERVICE_LABELS = {
  gateway:   'Gateway',
  llm_agent: 'LLM Agent',
  embedding: 'Embedding',
  reranker:  'Reranker',
  rag:       'RAG Orchestrator',
  files:     'File Service',
  vector_db: 'Vector DB',
  memory:    'Memory',
}

/* ── ServiceCard ────────────────────────────────────────── */
function ServiceCard({ name, info, index = 0 }) {
  const cfg = STATUS_CONFIG[info.status] || STATUS_CONFIG.unknown
  const Icon = cfg.icon

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="relative overflow-hidden rounded-2xl border p-4 transition-all duration-200 hover:shadow-md"
      style={{
        background: 'var(--surface-elevated)',
        borderColor: cfg.border,
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div className="absolute inset-y-0 left-0 w-0.5" style={{ background: cfg.iconColor }} />
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl" style={{ background: cfg.bg, color: cfg.iconColor }}>
          <Server size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-[13px] font-semibold text-text-primary">{SERVICE_LABELS[name] || name}</span>
            <Badge variant={cfg.badgeVariant} size="xs" dot>{cfg.label}</Badge>
          </div>
          <p className="mt-1 truncate text-xs text-text-muted">
            {info.message || (info.status === 'healthy' ? 'Responding normally' : 'Service requires attention')}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-border/70 pt-2.5">
        <span className="flex items-center gap-1.5 text-xs text-text-muted">
          <Icon size={11} style={{ color: cfg.iconColor }} /> Health check
        </span>
        {info.port && (
          <span className="rounded-md bg-bg-tertiary px-1.5 py-0.5 font-mono text-xs text-text-muted">:{info.port}</span>
        )}
      </div>
    </motion.div>
  )
}

/* ── CircuitBreakerPanel ────────────────────────────────── */
function CircuitBreakerPanel({ breakers }) {
  const entries = Object.entries(breakers || {})
  if (entries.length === 0) {
    return (
      <div className="py-8 text-center text-[13px]" style={{ color: 'var(--fg-soft)' }}>
        No circuit breakers registered yet
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {entries.map(([name, m]) => {
        const state  = m.state || 'closed'
        const cbCfg  = CB_STATE[state] || CB_STATE.closed
        const total  = m.total_calls || 0
        const failRate = total > 0 ? ((m.total_failures / total) * 100).toFixed(1) : '0.0'
        const failPct  = parseFloat(failRate)
        const barColor = failPct > 50 ? 'var(--danger)' : failPct > 20 ? 'var(--warning)' : 'var(--success)'

        return (
          <div
            key={name}
            className="rounded-lg p-3"
            style={{ background: 'var(--surface-hover)', border: '1px solid var(--border)' }}
          >
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-[13px] font-semibold capitalize" style={{ color: 'var(--fg)' }}>
                {name.replace(/_/g, ' ')}
              </span>
              <Badge variant={cbCfg.variant} size="xs">{cbCfg.label}</Badge>
            </div>
            <div className="grid grid-cols-4 gap-2 mb-2.5">
              {[
                { label: 'Calls',    value: total,               color: 'var(--fg)'      },
                { label: 'OK',       value: m.total_successes||0, color: 'var(--success)' },
                { label: 'Fail',     value: m.total_failures||0,  color: 'var(--danger)'  },
                { label: 'Rate',     value: `${failRate}%`,        color: 'var(--fg-muted)'},
              ].map(({ label, value, color }) => (
                <div key={label}>
                  <div className="label-xs mb-0.5">{label}</div>
                  <div className="text-[13px] font-mono font-semibold" style={{ color }}>{value}</div>
                </div>
              ))}
            </div>
            <ProgressBar
              value={Math.min(100, failPct)}
              color={barColor}
              track="bg-border"
              aria-label="Failure rate"
            />
          </div>
        )
      })}
    </div>
  )
}

/* ── RateLimiterPanel ───────────────────────────────────── */
function RateLimiterPanel({ metrics }) {
  if (!metrics || Object.keys(metrics).length === 0) {
    return (
      <div className="py-8 text-center text-[13px]" style={{ color: 'var(--fg-soft)' }}>
        Rate limiter metrics not available
      </div>
    )
  }

  const total = (metrics.total_allowed || 0) + (metrics.total_rejected || 0)
  const rejectRate = total > 0
    ? `${(((metrics.total_rejected || 0) / total) * 100).toFixed(1)}%`
    : '0%'

  const items = [
    { icon: CheckCircle2, label: 'Allowed',     value: metrics.total_allowed || 0,     variant: 'success' },
    { icon: ShieldOff,    label: 'Rejected',    value: metrics.total_rejected || 0,    variant: 'danger'  },
    { icon: Zap,          label: 'Active IPs',  value: metrics.active_ip_buckets || 0, variant: 'info'    },
    { icon: Gauge,        label: 'Reject Rate', value: rejectRate,                      variant: 'warning' },
  ]

  return (
    <div className="grid grid-cols-2 gap-3">
      {items.map(({ icon: Icon, label, value, variant }) => (
        <div
          key={label}
          className="rounded-lg p-3"
          style={{ background: 'var(--surface-hover)', border: '1px solid var(--border)' }}
        >
          <div className="label-xs mb-1.5">{label}</div>
          <div className="flex items-center gap-2">
            <Icon size={14} style={{ color: `var(--${variant === 'success' ? 'success' : variant === 'danger' ? 'danger' : variant === 'info' ? 'info' : 'warning'})` }} />
            <span className="text-xl font-bold font-mono" style={{ color: 'var(--fg)' }}>{value}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

/* ── Mini sparkline ─────────────────────────────────────── */
function MiniSparkline({ data, height = 28 }) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data, 1)
  const w   = 100
  const points = data.map((v, i) => `${(i / (data.length - 1)) * w},${height - (v / max) * height}`).join(' ')
  return (
    <svg width={w} height={height} className="opacity-60">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--success)' }} />
    </svg>
  )
}

/* ── Main component ─────────────────────────────────────── */
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
