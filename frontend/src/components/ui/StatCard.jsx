'use client'

import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * KPI stat card — label, value, optional sub-label, icon, and trend indicator.
 */
export default function StatCard({
  label,
  value,
  subLabel,
  icon: Icon,
  trend,        // 'up' | 'down' | 'neutral'
  trendLabel,
  variant = 'default', // 'default' | 'success' | 'warning' | 'danger' | 'info'
  className = '',
  style = {},
}) {
  const variantColors = {
    default: { icon: 'var(--primary)',  bg: 'var(--primary-soft)' },
    success: { icon: 'var(--success)',  bg: 'var(--success-soft)' },
    warning: { icon: 'var(--warning)',  bg: 'var(--warning-soft)' },
    danger:  { icon: 'var(--danger)',   bg: 'var(--danger-soft)'  },
    info:    { icon: 'var(--info)',     bg: 'var(--info-soft)'    },
  }
  const colors = variantColors[variant] || variantColors.default

  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus
  const trendColor = trend === 'up' ? 'var(--success)' : trend === 'down' ? 'var(--danger)' : 'var(--fg-soft)'

  return (
    <div
      className={cn('rounded-xl p-4 flex flex-col gap-3', className)}
      style={{
        background: 'var(--surface)',
        border:     '1px solid var(--border)',
        boxShadow:  'var(--shadow-sm)',
        ...style,
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="label-xs">{label}</span>
        {Icon && (
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: colors.bg }}
          >
            <Icon size={15} style={{ color: colors.icon }} />
          </div>
        )}
      </div>
      <div>
        <div className="text-2xl font-bold tracking-tight" style={{ color: 'var(--fg)' }}>
          {value}
        </div>
        {subLabel && (
          <div className="text-[13px] mt-0.5" style={{ color: 'var(--fg-soft)' }}>
            {subLabel}
          </div>
        )}
      </div>
      {trend && trendLabel && (
        <div className="flex items-center gap-1 text-xs font-medium" style={{ color: trendColor }}>
          <TrendIcon size={12} />
          {trendLabel}
        </div>
      )}
    </div>
  )
}
