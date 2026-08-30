'use client'

import { useRef } from 'react'
import { cn } from '@/lib/utils'

/**
 * An underlined tab strip with the full ARIA tab pattern.
 *
 * Written once here rather than per feature because the keyboard contract
 * is the part everyone reimplements wrong: arrow keys move between tabs,
 * Home and End jump to the ends, and only the active tab is in the page's
 * tab order. `Tabs` renders the strip; the caller renders one `TabPanel`
 * for the active tab, so a heavy panel is never mounted while hidden.
 */
export default function Tabs({ tabs = [], value, onChange, label, className = '' }) {
  const stripRef = useRef(null)

  const move = (event) => {
    const keys = { ArrowRight: 1, ArrowLeft: -1 }
    const index = tabs.findIndex((tab) => tab.id === value)
    let next = null
    if (event.key in keys) next = (index + keys[event.key] + tabs.length) % tabs.length
    if (event.key === 'Home') next = 0
    if (event.key === 'End') next = tabs.length - 1
    if (next === null) return
    event.preventDefault()
    onChange(tabs[next].id)
    stripRef.current?.querySelectorAll('[role="tab"]')[next]?.focus()
  }

  return (
    <div
      ref={stripRef}
      role="tablist"
      aria-label={label}
      onKeyDown={move}
      className={cn('flex gap-1 overflow-x-auto border-b', className)}
      style={{ borderColor: 'var(--border)' }}
    >
      {tabs.map((tab) => {
        const active = tab.id === value
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={active}
            aria-controls={`panel-${tab.id}`}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(tab.id)}
            className={cn(
              'relative flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-2 text-[13px] font-medium',
              'transition-colors duration-150 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]'
            )}
            style={{
              color: active ? 'var(--fg)' : 'var(--fg-soft)',
              boxShadow: active ? 'inset 0 -2px 0 0 var(--primary)' : 'none',
            }}
          >
            {tab.label}
            {tab.badge != null && (
              <span
                className="rounded-full px-1.5 text-[11px] tabular-nums"
                style={{
                  background: tab.tone === 'danger' ? 'var(--danger-soft)' : 'var(--surface-hover)',
                  color: tab.tone === 'danger' ? 'var(--danger)' : 'var(--fg-muted)',
                }}
              >
                {tab.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/** The panel for one tab. Rendered only while its tab is the active one. */
export function TabPanel({ id, children, className = '' }) {
  return (
    <div
      role="tabpanel"
      id={`panel-${id}`}
      aria-labelledby={`tab-${id}`}
      // The panel is focusable so a keyboard user can scroll it, which means
      // it needs to say so when it is focused. An inset ring does that without
      // the layout shift an outer ring would cause inside a tab shell.
      tabIndex={0}
      className={cn(
        'pt-4 rounded-lg focus-visible:outline-hidden',
        'focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--ring)]',
        className
      )}
    >
      {children}
    </div>
  )
}
