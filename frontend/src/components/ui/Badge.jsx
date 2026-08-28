'use client'

import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import { STATUS_TONE, resolveToneName } from '@/components/status/statusTone'

/**
 * A small label. Colour comes from the shared status tone table rather than
 * from a second copy of it that lived here — `variant` names that predate the
 * tone vocabulary (`error`, `accent`, `default`) still resolve, via
 * `resolveToneName`.
 *
 * For an actual status, prefer StatusIndicator: it guarantees the icon and
 * the accessible label that a bare Badge leaves optional.
 */

const badgeVariants = cva(
  'inline-flex items-center font-medium border select-none whitespace-nowrap',
  {
    variants: {
      size: {
        xs: 'px-1.5 py-0.5 text-xs gap-1 rounded',
        sm: 'px-2 py-0.5 text-xs gap-1 rounded-md',
        md: 'px-2.5 py-1 text-[13px] gap-1.5 rounded-md',
      },
    },
    defaultVariants: { size: 'sm' },
  }
)

/** The two variants that are not status tones: they style the chrome, not a state. */
const NON_TONE_VARIANTS = {
  primary: { color: 'var(--primary)', background: 'var(--primary-soft)', borderColor: 'transparent' },
  outline: { color: 'var(--fg-muted)', background: 'transparent', borderColor: 'var(--border)' },
}

export default function Badge({
  children,
  variant = 'default',
  size = 'sm',
  icon: Icon,
  pulse = false,
  dot = false,
  spin = false,
  className = '',
  style = {},
  ...props
}) {
  const override = NON_TONE_VARIANTS[variant]
  const tone = STATUS_TONE[resolveToneName(variant)]
  const surface = override ?? { color: tone.fg, background: tone.bg, borderColor: tone.border }

  return (
    <span
      className={cn(badgeVariants({ size }), pulse && 'animate-pulse', className)}
      style={{ ...surface, ...style }}
      {...props}
    >
      {dot && (
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: surface.color }}
          aria-hidden="true"
        />
      )}
      {Icon && (
        <Icon
          size={size === 'xs' ? 10 : 12}
          aria-hidden="true"
          className={cn('shrink-0', spin && 'animate-spin')}
        />
      )}
      {children}
    </span>
  )
}
