'use client'

import { CircleDot } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import EmptyState from '@/components/feedback/EmptyState'
import ProgressBar from '@/components/ui/ProgressBar'
import { ShieldCheck } from 'lucide-react'
import { CB_STATE } from './healthConfig'

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

export default CircuitBreakerPanel
