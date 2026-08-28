'use client'

import { cn } from '@/lib/utils'

/**
 * "There is nothing here yet" — as distinct from loading and from failing.
 *
 * The icon used to float on a three-second infinite loop. Idle UI should be
 * calm, and an empty list is the most idle thing on screen, so the motion is
 * gone; the halo alone carries the emphasis.
 */
const SIZES = {
  sm: { iconSize: 28, iconBox: 'w-12 h-12', titleClass: 'text-[15px]', descClass: 'text-[13px]' },
  md: { iconSize: 36, iconBox: 'w-16 h-16', titleClass: 'text-lg', descClass: 'text-[15px]' },
  lg: { iconSize: 48, iconBox: 'w-20 h-20', titleClass: 'text-xl', descClass: 'text-[15px]' },
}

export default function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  size = 'md',
  className = '',
}) {
  const { iconSize, iconBox, titleClass, descClass } = SIZES[size] || SIZES.md

  return (
    <div
      role="status"
      className={cn('flex flex-col items-center justify-center text-center py-16 px-6 gap-5', className)}
    >
      {Icon && (
        <div
          className={cn('rounded-2xl flex items-center justify-center', iconBox)}
          style={{
            background: 'var(--primary-soft)',
            boxShadow: '0 0 0 8px var(--primary-soft)',
          }}
        >
          <Icon size={iconSize} strokeWidth={1.5} aria-hidden="true" style={{ color: 'var(--primary)' }} />
        </div>
      )}
      <div className="space-y-2 max-w-xs">
        <h3 className={cn('font-semibold', titleClass)} style={{ color: 'var(--fg)' }}>
          {title}
        </h3>
        {description && (
          <p className={cn('leading-relaxed', descClass)} style={{ color: 'var(--fg-muted)' }}>
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
