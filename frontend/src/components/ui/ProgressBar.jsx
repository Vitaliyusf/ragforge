'use client'

import { cn } from '@/lib/utils'

const THICKNESS = {
  xs: 'h-1',
  sm: 'h-1.5',
  md: 'h-2',
}

/**
 * Track-and-fill progress bar.
 *
 * The same track/fill markup had been written out seven times across the
 * trace panel, training tab, health dashboard, message list and metrics
 * modal. `value` is a percentage; pass null to render an empty track.
 */
export default function ProgressBar({
  value,
  color = 'var(--primary)',
  thickness = 'sm',
  track = 'bg-bg-tertiary',
  fillOpacity,
  className = '',
  'aria-label': ariaLabel,
}) {
  const pct = value == null ? null : Math.max(0, Math.min(100, value))

  return (
    <div
      className={cn('w-full overflow-hidden rounded-full', track, THICKNESS[thickness], className)}
      role="progressbar"
      aria-valuenow={pct ?? undefined}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel}
    >
      {pct != null ? (
        <div
          className="h-full rounded-full transition-[width] duration-500 ease-out"
          style={{ width: `${pct}%`, backgroundColor: color, opacity: fillOpacity }}
        />
      ) : null}
    </div>
  )
}
