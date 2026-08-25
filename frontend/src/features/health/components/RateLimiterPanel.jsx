'use client'

import { CheckCircle2, Gauge, ShieldOff, Zap } from 'lucide-react'
import EmptyState from '@/components/ui/EmptyState'
import ProgressBar from '@/components/ui/ProgressBar'

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

export default RateLimiterPanel
