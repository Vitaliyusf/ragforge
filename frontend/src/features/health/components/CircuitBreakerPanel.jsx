'use client'

import { CircleDot } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import EmptyState from '@/components/feedback/EmptyState'
import ProgressBar from '@/components/ui/ProgressBar'
import { ShieldCheck } from 'lucide-react'
import { CB_STATE } from './healthConfig'
import { useI18n } from '@/i18n'

function CircuitBreakerPanel({ breakers }) {
  const { t } = useI18n()
  const entries = Object.entries(breakers || {})
  if (entries.length === 0) {
    return (
      <div className="py-8 text-center text-[13px]" style={{ color: 'var(--fg-soft)' }}>
        {t('health.noBreakers')}
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
              {/* The breaker is named after the dependency it protects —
                  a backend key, not copy. */}
              <span dir="ltr" className="text-[13px] font-semibold capitalize [unicode-bidi:isolate]" style={{ color: 'var(--fg)' }}>
                {name.replace(/_/g, ' ')}
              </span>
              <Badge variant={cbCfg.variant} size="xs">{t(cbCfg.labelKey)}</Badge>
            </div>
            <div className="grid grid-cols-4 gap-2 mb-2.5">
              {[
                { labelKey: 'health.calls', value: total,                color: 'var(--fg)'      },
                { labelKey: 'health.ok',    value: m.total_successes||0, color: 'var(--success)' },
                { labelKey: 'health.fail',  value: m.total_failures||0,  color: 'var(--danger)'  },
                { labelKey: 'health.rate',  value: `${failRate}%`,       color: 'var(--fg-muted)'},
              ].map(({ labelKey, value, color }) => (
                <div key={labelKey}>
                  <div className="label-xs mb-0.5">{t(labelKey)}</div>
                  <div className="text-[13px] font-mono font-semibold" style={{ color }}>{value}</div>
                </div>
              ))}
            </div>
            <ProgressBar
              value={Math.min(100, failPct)}
              color={barColor}
              track="bg-border"
              aria-label={t('health.failureRate')}
            />
          </div>
        )
      })}
    </div>
  )
}

export default CircuitBreakerPanel
