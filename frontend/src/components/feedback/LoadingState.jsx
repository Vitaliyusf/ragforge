'use client'

import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { usePrefersReducedMotion } from '@/lib/accessibility/usePrefersReducedMotion'

/**
 * "We are fetching this, it is not broken and it is not empty."
 *
 * Deliberately has no `progress` prop. Nothing in the app knows how far
 * along a fetch is, and a bar that moves on a timer is a lie about state.
 * Where a real percentage exists, use ProgressBar instead.
 *
 * `minHeight` reserves the space the loaded content will occupy so the
 * transition out of the loading state does not shift the layout.
 */
export default function LoadingState({
  label = 'Loading…',
  minHeight,
  className = '',
}) {
  const reducedMotion = usePrefersReducedMotion()

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={cn('flex flex-col items-center justify-center gap-3 px-6 py-10 text-center', className)}
      style={minHeight ? { minHeight } : undefined}
    >
      <Loader2
        size={20}
        aria-hidden="true"
        className={cn('shrink-0', !reducedMotion && 'animate-spin')}
        style={{ color: 'var(--fg-soft)' }}
      />
      <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
        {label}
      </p>
    </div>
  )
}
