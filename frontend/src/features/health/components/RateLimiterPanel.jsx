'use client'

import { CheckCircle2, Gauge, ShieldOff, Zap } from 'lucide-react'
import EmptyState from '@/components/feedback/EmptyState'
import ProgressBar from '@/components/ui/ProgressBar'
import { useI18n } from '@/i18n'

function RateLimiterPanel({ metrics }) {
  const { t } = useI18n()
  if (!metrics || Object.keys(metrics).length === 0) {
    return (
      <div className="py-8 text-center text-[13px]" style={{ color: 'var(--fg-soft)' }}>
        {t('health.noRateLimiterMetrics')}
      </div>
    )
  }

  const total = (metrics.total_allowed || 0) + (metrics.total_rejected || 0)
  const rejectRate = total > 0
    ? `${(((metrics.total_rejected || 0) / total) * 100).toFixed(1)}%`
    : '0%'

  const items = [
    { icon: CheckCircle2, labelKey: 'health.allowed',    value: metrics.total_allowed || 0,     variant: 'success' },
    { icon: ShieldOff,    labelKey: 'health.rejected',   value: metrics.total_rejected || 0,    variant: 'danger'  },
    { icon: Zap,          labelKey: 'health.activeIps',  value: metrics.active_ip_buckets || 0, variant: 'info'    },
    { icon: Gauge,        labelKey: 'health.rejectRate', value: rejectRate,                     variant: 'warning' },
  ]

  return (
    <div className="grid grid-cols-2 gap-3">
      {items.map(({ icon: Icon, labelKey, value, variant }) => (
        <div
          key={labelKey}
          className="rounded-lg p-3"
          style={{ background: 'var(--surface-hover)', border: '1px solid var(--border)' }}
        >
          <div className="label-xs mb-1.5">{t(labelKey)}</div>
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

export default RateLimiterPanel
