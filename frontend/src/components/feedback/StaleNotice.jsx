'use client'

import { AlertTriangle, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { STATUS_TONES, resolveTone } from '@/components/status/statusTone'

/**
 * A strip above content that is real but not current.
 *
 * Two cases, both of which have to keep the content on screen:
 *
 *   `stale`   — this is the last good data; a refresh is failing or pending.
 *   `partial` — some of the sources answered and some did not.
 *
 * Neither is an error state, because replacing a partly-useful view with a
 * red box costs the user the data they already had.
 */
const VARIANTS = {
  stale: {
    tone: STATUS_TONES.NEUTRAL,
    icon: Clock,
    defaultMessage: 'Showing the last data we received.',
  },
  partial: {
    tone: STATUS_TONES.WARNING,
    icon: AlertTriangle,
    defaultMessage: 'Some sources did not respond, so this view is incomplete.',
  },
}

export default function StaleNotice({
  variant = 'stale',
  message,
  action,
  className = '',
}) {
  const config = VARIANTS[variant] ?? VARIANTS.stale
  const tone = resolveTone(config.tone)
  const Icon = config.icon

  return (
    <div
      role="status"
      aria-live="polite"
      data-variant={variant}
      className={cn(
        'flex items-center gap-2 rounded-control border px-3 py-2 text-[13px]',
        className
      )}
      style={{ color: tone.fg, background: tone.bg, borderColor: tone.border }}
    >
      <Icon size={14} aria-hidden="true" className="shrink-0" />
      <span className="min-w-0 flex-1 text-start">{message ?? config.defaultMessage}</span>
      {action}
    </div>
  )
}
