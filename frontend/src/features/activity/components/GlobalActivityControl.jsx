'use client'

/**
 * The one place the header says what is happening.
 *
 * It is a status *and* a disclosure: the button always carries text and an
 * icon (never colour alone), and opening it lists the work that is actually
 * running — one row per activity a feature published, with nothing invented
 * to fill the panel out.
 */

import { useEffect, useRef, useState } from 'react'
import StatusIndicator from '@/components/status/StatusIndicator'
import { resolveTone } from '@/components/status/statusTone'
import { cn } from '@/lib/utils'
import { useI18n } from '@/i18n'
import { GLOBAL_ACTIVITY_STATES } from '../globalActivity'

const EMPTY_COPY_KEYS = {
  [GLOBAL_ACTIVITY_STATES.READY]: 'activity.emptyReady',
  [GLOBAL_ACTIVITY_STATES.DISCONNECTED]: 'activity.emptyDisconnected',
}

export default function GlobalActivityControl({ summary }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)

  // Dismissal listeners exist only while the panel is open, matching the
  // rest of the header's popovers.
  useEffect(() => {
    if (!open) return undefined
    const outsideHandler = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) setOpen(false)
    }
    const keyHandler = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', outsideHandler)
    document.addEventListener('keydown', keyHandler)
    return () => {
      document.removeEventListener('mousedown', outsideHandler)
      document.removeEventListener('keydown', keyHandler)
    }
  }, [open])

  // `label` on the summary is the canonical English text; `labelKey` is what
  // the reader actually sees. Both exist because the summary is derived by a
  // pure module that has no locale of its own.
  const summaryLabel = summary.labelKey
    ? t(summary.labelKey, summary.labelVars)
    : summary.label

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={t('activity.workspace', { label: summaryLabel })}
        data-activity-state={summary.state}
        data-testid="global-activity"
        className={cn(
          'flex h-9 items-center rounded-xl px-1.5 transition-colors duration-150',
          'focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
          open ? 'bg-[var(--surface-hover)]' : 'hover:bg-[var(--surface-hover)]'
        )}
      >
        <StatusIndicator tone={summary.tone} label={summaryLabel} size="sm" shape="inline" />
      </button>

      {open && (
        <div
          className="animate-dropdown-in absolute end-0 top-full z-[1000] mt-2 w-[min(20rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border"
          style={{
            background: 'var(--surface-elevated)',
            borderColor: 'var(--border)',
            boxShadow: 'var(--shadow-xl)',
          }}
        >
          <div className="border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
            <p className="text-[15px] font-semibold text-[var(--fg)]">{t('activity.title')}</p>
            <p className="mt-0.5 text-xs text-[var(--fg-soft)]">{summaryLabel}</p>
          </div>

          {summary.items.length === 0 ? (
            <p className="px-4 py-3 text-[13px] text-[var(--fg-soft)]">
              {t(EMPTY_COPY_KEYS[summary.state] || 'activity.emptyDefault')}
            </p>
          ) : (
            <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {summary.items.map((item) => (
                <li key={item.feature} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium text-[var(--fg)]">
                      {t(item.workKey)}
                    </span>
                    <span className="block truncate text-xs text-[var(--fg-soft)]">
                      {t(item.featureLabelKey)}
                      {item.detail ? ` · ${item.detail}` : ''}
                    </span>
                  </span>
                  <StatusIndicator
                    tone={item.tone}
                    label={t(item.stateLabelKey)}
                    size="sm"
                    data-domain="execution"
                    data-state={item.state}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * The mark on the logo.
 *
 * Kept deliberately mute: it shares the control's tone so the brand corner
 * agrees with the status text, and it is `aria-hidden` because the control
 * beside it already carries the words. It was previously a permanently lit
 * accent dot that meant nothing at all.
 */
export function ActivityDot({ summary }) {
  const tone = resolveTone(summary.tone)
  return (
    <span
      aria-hidden="true"
      data-testid="logo-activity-dot"
      data-activity-state={summary.state}
      className="absolute -end-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2"
      style={{ background: tone.fg, borderColor: 'var(--surface-elevated)' }}
    />
  )
}
