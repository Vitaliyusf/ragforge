'use client'

import { AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ltrIsolateProps } from '@/lib/accessibility/direction'

/**
 * A failure the user may be able to do something about.
 *
 * `action` is a slot rather than an optional nicety: an error the user can
 * only stare at is a dead end, so every call site is pushed to supply a
 * retry, a way back, or an explanation of what to change.
 *
 * `detail` is for machine text — a request id, a status code, an error
 * name — and is isolated LTR so it stays readable inside RTL copy.
 */
export default function ErrorState({
  title = 'Something went wrong',
  description,
  detail,
  action,
  className = '',
}) {
  const isolate = ltrIsolateProps()

  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-surface border px-6 py-10 text-center',
        className
      )}
      style={{ borderColor: 'var(--border)', background: 'var(--danger-soft)' }}
    >
      <AlertTriangle size={22} aria-hidden="true" style={{ color: 'var(--danger)' }} className="shrink-0" />
      <div className="space-y-1.5 max-w-sm">
        <p className="font-semibold text-[15px]" style={{ color: 'var(--fg)' }}>
          {title}
        </p>
        {description && (
          <p className="text-[13px] leading-relaxed" style={{ color: 'var(--fg-muted)' }}>
            {description}
          </p>
        )}
        {detail && (
          <p
            {...isolate}
            className={cn('font-mono text-xs', isolate.className)}
            style={{ color: 'var(--fg-soft)' }}
          >
            {detail}
          </p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}
