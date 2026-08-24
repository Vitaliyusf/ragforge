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
    <div className={cn('mb-8 flex flex-col items-start justify-between gap-4 sm:flex-row', className)}>
      <div className="flex items-center gap-3.5 min-w-0">
        {Icon && (
          <div
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl"
            style={{ background: 'var(--primary-soft)' }}
          >
            <Icon size={22} strokeWidth={1.9} style={{ color: 'var(--primary)' }} />
          </div>
        )}
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1
              className="truncate text-[28px] font-semibold leading-tight tracking-[-0.02em]"
              style={{ color: 'var(--fg)' }}
            >
              {title}
            </h1>
            {badge}
          </div>
          {description && (
            <p className="mt-1.5 text-[15px] leading-relaxed" style={{ color: 'var(--fg-muted)' }}>
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
