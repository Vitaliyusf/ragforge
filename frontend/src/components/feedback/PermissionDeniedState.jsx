'use client'

import { Lock } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * "This exists, you just cannot see it."
 *
 * Distinct from ErrorState on purpose: nothing failed, retrying will not
 * help, and the recovery is social rather than technical. Saying so is what
 * stops the user retrying a request that will never succeed.
 */
export default function PermissionDeniedState({
  title = 'You do not have access to this',
  description = 'Ask an administrator to grant your account access.',
  action,
  className = '',
}) {
  return (
    <div
      role="status"
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-surface border px-6 py-10 text-center',
        className
      )}
      style={{ borderColor: 'var(--border)', background: 'var(--surface-hover)' }}
    >
      <Lock size={22} aria-hidden="true" style={{ color: 'var(--fg-soft)' }} className="shrink-0" />
      <div className="space-y-1.5 max-w-sm">
        <p className="font-semibold text-[15px]" style={{ color: 'var(--fg)' }}>
          {title}
        </p>
        <p className="text-[13px] leading-relaxed" style={{ color: 'var(--fg-muted)' }}>
          {description}
        </p>
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}
