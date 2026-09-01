'use client'

import { useMemo } from 'react'
import {
  Activity, Server, RefreshCw, AlertTriangle, CheckCircle2, XCircle, Gauge, HeartPulse, ShieldCheck,
} from 'lucide-react'
import Button from '@/components/ui/Button'
import PageHeader from '@/components/ui/PageHeader'
import StatCard from '@/components/ui/StatCard'
import EmptyState from '@/components/feedback/EmptyState'
import ProgressBar from '@/components/ui/ProgressBar'
import { useHealth } from '../hooks/useHealth'

import ServiceCard from './ServiceCard'
import CircuitBreakerPanel from './CircuitBreakerPanel'
import RateLimiterPanel from './RateLimiterPanel'
import MiniSparkline from './MiniSparkline'
import DomainStatus from '@/components/status/DomainStatus'
import { STATUS_DOMAINS } from '@/components/status/statusDomains'
import { FreshnessBadge, ScopeBadge } from '@/components/observability/MetricMeta'
import {
  METRIC_SOURCE,
  describeFreshness,
  describeScope,
} from '@/lib/observability/metricMeta'
import { STATUS_CONFIG, SERVICE_LABELS } from './healthConfig'
import { useI18n } from '@/i18n'
import { intlLocale } from '@/lib/formatting/datetime'

/**
 * Health polls every 5s, so its patience is far shorter than the metrics
 * tab's: half a minute without a reading is already worth saying, and two
 * minutes of it means the probe results on screen describe the past.
 */
const HEALTH_FRESHNESS = { delayedAfterMs: 30_000, staleAfterMs: 120_000 }

/**
 * What these probes do and do not measure — see `health.probeScopeNote`.
 *
 * Readiness says a service will accept traffic. It says nothing about whether
 * that traffic is being served within any objective, and nothing collected
 * here does — so this page must not be read as an SLO view.
 */
export default function HealthDashboard() {
  const { locale, t } = useI18n()
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

  // Probes are platform-wide, and the reading has an age like any other.
  const probeScope = describeScope({ source: METRIC_SOURCE.PROMETHEUS })
  const probeFreshness = describeFreshness(
    health?.timestamp ? health.timestamp * 1000 : null,
    HEALTH_FRESHNESS
  )

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
        title={t('health.systemHealth')}
        description={health?.timestamp
          ? t('health.lastUpdated', {
              time: new Date(health.timestamp * 1000).toLocaleTimeString(intlLocale(locale)),
            })
          : t('health.subtitle')}
        icon={HeartPulse}
        badge={
          <span className="flex flex-wrap items-center gap-2">
            {health && (
              <DomainStatus domain={STATUS_DOMAINS.SERVICE} state={health.status} size="md" />
            )}
            <ScopeBadge scope={probeScope} />
            <FreshnessBadge freshness={probeFreshness} />
          </span>
        }
        actions={
          <div className="flex items-center gap-2">
            {healthTimeline.length > 1 && <MiniSparkline data={healthTimeline} />}
            <Button variant="secondary" size="sm" onClick={refresh} disabled={loading}
              leftIcon={<RefreshCw size={13} className={loading ? 'animate-spin' : ''} />}>
              {t('common.refresh')}
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
        style={{ borderColor: overallCfg.border, boxShadow: 'var(--shadow-md)' }}
      >
        <div className="pointer-events-none absolute -end-16 -top-20 h-56 w-56 rounded-full bg-primary-soft blur-3xl" />
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
                  ? t('health.allOperational')
                  : health?.status === 'degraded'
                    ? t('health.someDegraded')
                    : health?.status === 'unhealthy'
                      ? t('health.interventionRequired')
                      : t('health.waitingForTelemetry')}
              </h2>
              <DomainStatus domain={STATUS_DOMAINS.SERVICE} state={health?.status} size="md" />
            </div>
            <p className="mt-1 text-[15px] text-text-muted">
              {t('health.respondingNormally', { healthy: healthyCount, total: totalServices })}
            </p>
            <div className="mt-4 flex items-center gap-3">
              <ProgressBar
                value={healthPercent}
                color={overallCfg.iconColor}
                thickness="md"
                className="flex-1"
                aria-label={t('health.serviceHealth')}
              />
              <span className="text-[13px] font-semibold tabular-nums" style={{ color: overallCfg.iconColor }}>{healthPercent}%</span>
            </div>
            <p className="mt-3 text-xs" style={{ color: 'var(--fg-soft)' }}>
              {t('health.probeScopeNote')}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 md:w-[260px]">
            {[
              ['health.healthy', healthyCount, 'var(--success)'],
              ['health.degraded', degradedCount, 'var(--warning)'],
              ['health.down', unhealthyCount, 'var(--danger)'],
            ].map(([labelKey, value, color]) => (
              <div key={labelKey} className="rounded-xl border border-border px-3 py-2.5 text-center backdrop-blur">
                <div className="text-xl font-semibold tabular-nums" style={{ color }}>{value}</div>
                <div className="mt-0.5 text-xs uppercase tracking-wide text-text-muted">{t(labelKey)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label={t('health.monitored')}
          value={totalServices}
          icon={Server}
          variant="info"
          subLabel={t('health.registeredServices')}
        />
        <StatCard
          label={t('health.healthy')}
          value={healthyCount}
          icon={CheckCircle2}
          variant="success"
          subLabel={t('health.ofServices', { total: totalServices })}
        />
        <StatCard label={t('health.degraded')} value={degradedCount} icon={AlertTriangle} variant="warning" />
        <StatCard label={t('health.unhealthy')} value={unhealthyCount} icon={XCircle} variant="danger" />
      </div>

      {/* ── Services grid ── */}
      <div
        className="rounded-2xl p-4 shadow-sm md:p-5"
        style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Server size={14} style={{ color: 'var(--fg-soft)' }} />
          <div>
            <span className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>
              {t('health.serviceMap')}
            </span>
            <p className="mt-0.5 text-xs text-text-muted">{t('health.serviceMapDescription')}</p>
          </div>
          <span className="ms-auto text-[13px]" style={{ color: 'var(--fg-soft)' }}>
            {t('health.online', { healthy: healthyCount, total: totalServices })}
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
            title={t('health.noServiceData')}
            description={t('health.noServiceDataDescription')}
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
              <span className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>
                {t('health.circuitBreakers')}
              </span>
              <p className="mt-0.5 text-xs text-text-muted">{t('health.circuitBreakersDescription')}</p>
            </div>
          </div>
          <CircuitBreakerPanel breakers={health?.circuit_breakers} />
        </div>

        <div className="rounded-2xl p-4 shadow-sm md:p-5" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border)' }}>
          <div className="flex items-center gap-2 mb-4">
            <Gauge size={14} style={{ color: 'var(--fg-soft)' }} />
            <div>
              <span className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>
                {t('health.rateLimiter')}
              </span>
              <p className="mt-0.5 text-xs text-text-muted">{t('health.rateLimiterDescription')}</p>
            </div>
          </div>
          <RateLimiterPanel metrics={health?.rate_limiter} />
        </div>
      </div>
    </div>
  )
}
