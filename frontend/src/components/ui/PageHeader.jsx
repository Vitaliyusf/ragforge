'use client'

import { cn } from '@/lib/utils'

/**
 * Reusable page-level header: title, description, optional badges/actions.
 */
export default function PageHeader({
  title,
  description,
  icon: Icon,
  actions,
  badge,
  className = '',
}) {
  return (
    <div className={cn('mb-7 flex flex-col items-start justify-between gap-4 sm:flex-row', className)}>
      <div className="flex items-center gap-3 min-w-0">
        {Icon && (
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border"
            style={{
              background: 'var(--gradient-subtle)',
              borderColor: 'var(--border)',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <Icon size={20} strokeWidth={1.8} style={{ color: 'var(--primary)' }} />
          </div>
        )}
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="truncate text-xl font-semibold tracking-tight" style={{ color: 'var(--fg)' }}>
              {title}
            </h1>
            {badge}
          </div>
          {description && (
            <p className="mt-1 text-sm" style={{ color: 'var(--fg-muted)' }}>
              {description}
            </p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 sm:self-center">
          {actions}
        </div>
      )}
    </div>
  )
}
