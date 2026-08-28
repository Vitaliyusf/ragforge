'use client'

import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import { usePrefersReducedMotion } from '@/lib/accessibility/usePrefersReducedMotion'
import { resolveTone, resolveToneName } from './statusTone'

/**
 * The canonical way to show a status.
 *
 * Three cues, always together: an icon (shape), a label (text) and a tone
 * (colour). Colour is the one that is allowed to be missing — `iconOnly`
 * drops the visible text but keeps it as the accessible name, and nothing
 * drops the icon. That is what stops a status from being colour-only.
 *
 * Continuous motion is reserved for the `live` tone, and suppressed entirely
 * when the viewer asked for reduced motion.
 */

const indicatorVariants = cva(
  'inline-flex items-center font-medium select-none whitespace-nowrap border',
  {
    variants: {
      size: {
        sm: 'gap-1 rounded-md px-2 py-0.5 text-xs',
        md: 'gap-1.5 rounded-control px-2.5 py-1 text-[13px]',
      },
      shape: {
        badge: '',
        // Bare text + icon, for use inside a row that already has a surface.
        inline: 'border-transparent bg-transparent px-0 py-0',
      },
    },
    defaultVariants: { size: 'sm', shape: 'badge' },
  }
)

const ICON_PX = { sm: 12, md: 14 }

export default function StatusIndicator({
  tone = 'neutral',
  label,
  icon,
  size = 'sm',
  shape = 'badge',
  iconOnly = false,
  className = '',
  ...props
}) {
  const reducedMotion = usePrefersReducedMotion()
  const toneName = resolveToneName(tone)
  const toneStyle = resolveTone(toneName)
  const Icon = icon ?? toneStyle.icon
  const spin = toneStyle.live && !reducedMotion

  const surface =
    shape === 'inline'
      ? { color: toneStyle.fg }
      : { color: toneStyle.fg, background: toneStyle.bg, borderColor: toneStyle.border }

  return (
    <span
      className={cn(indicatorVariants({ size, shape }), className)}
      style={surface}
      data-tone={toneName}
      // Live work is an assertive-free announcement; terminal states are read
      // when the user reaches them rather than interrupting.
      role="status"
      aria-label={iconOnly ? label : undefined}
      {...props}
    >
      <Icon size={ICON_PX[size] ?? ICON_PX.sm} className={cn('shrink-0', spin && 'animate-spin')} aria-hidden="true" />
      {iconOnly ? null : label}
    </span>
  )
}
