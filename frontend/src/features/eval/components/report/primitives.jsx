'use client'

import { ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { resolveTone } from '@/components/status/statusTone'

/**
 * The run report's shared building blocks.
 *
 * Before this module the same bordered notice, the same table wrapper and
 * the same `<details>` block were written out once per eval surface, each
 * with its own padding and its own idea of what a warning looks like. One
 * copy each, so a change to how the report speaks is a change in one file.
 */

/** A bordered notice in one of the shared status tones. */
export function Callout({ tone = 'warning', icon: Icon, title, children, className = '' }) {
  const palette = resolveTone(tone)
  const IconComponent = Icon || palette.icon
  return (
    <div
      className={cn('rounded-xl px-4 py-3 text-[13px]', className)}
      style={{
        background: palette.bg,
        border: `1px solid ${palette.border === 'transparent' ? `${palette.fg}40` : palette.border}`,
        color: palette.fg,
      }}
    >
      <p className="flex items-center gap-2 text-[15px] font-semibold">
        <IconComponent size={15} aria-hidden="true" />
        {title}
      </p>
      <div className="mt-1.5">{children}</div>
    </div>
  )
}

/**
 * A report table with its own horizontal scroller.
 *
 * Every wide surface on this page scrolls inside itself; a table that
 * widened the page instead would push the whole report sideways on a
 * laptop. `columns` carries the header row so no caller re-writes the
 * `<thead>` markup and its alignment rules a seventh time.
 */
export function ReportTable({ caption, columns, children }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr style={{ color: 'var(--fg-muted)' }}>
            {columns.map((column) => (
              <th
                key={column.key || column.label}
                scope="col"
                className={cn(
                  'py-1.5 pr-3 font-medium',
                  column.align === 'right' ? 'text-right' : 'text-left'
                )}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

/** A body row of a report table. */
export function Row({ children, className = '' }) {
  return (
    <tr
      className={cn('border-t align-top', className)}
      style={{ borderColor: 'var(--border)' }}
    >
      {children}
    </tr>
  )
}

/** A numeric cell: right-aligned, tabular, muted. */
export function Num({ children, color = 'var(--fg-muted)' }) {
  return (
    <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color }}>
      {children}
    </td>
  )
}

/** A text cell. */
export function Cell({ children, className = '', color = 'var(--fg-muted)' }) {
  return (
    <td className={cn('py-1.5 pr-3', className)} style={{ color }}>
      {children}
    </td>
  )
}

/**
 * One collapsible detail block.
 *
 * `<details>` rather than a bespoke accordion: it is keyboard-operable,
 * announced correctly and findable by the browser's own in-page search
 * without any of that having to be written or tested here.
 */
export function Disclosure({ title, summary, tone, defaultOpen = false, children }) {
  return (
    <details className="group border-t" style={{ borderColor: 'var(--border)' }} open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-start gap-2 py-3 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
        <ChevronRight
          size={14}
          aria-hidden="true"
          className="mt-0.5 shrink-0 transition-transform duration-150 group-open:rotate-90"
          style={{ color: 'var(--fg-soft)' }}
        />
        <span className="min-w-0">
          <span
            className="block text-[13px] font-medium"
            style={{ color: tone === 'warning' ? 'var(--warning)' : 'var(--fg)' }}
          >
            {title}
          </span>
          {summary && (
            <span className="mt-0.5 block text-[12px]" style={{ color: 'var(--fg-soft)' }}>
              {summary}
            </span>
          )}
        </span>
      </summary>
      <div className="pb-4 pl-6">{children}</div>
    </details>
  )
}

/** A labelled figure, used wherever the report states a fact beside a word. */
export function Fact({ label, value, color }) {
  return (
    <div>
      <dt className="label-xs">{label}</dt>
      <dd className="mt-0.5 font-semibold tabular-nums" style={color ? { color } : undefined}>
        {value}
      </dd>
    </div>
  )
}

/** The report's own "there is nothing to show here, and why" line. */
export function Note({ children, tone }) {
  return (
    <p
      className="text-[13px]"
      style={{ color: tone ? resolveTone(tone).fg : 'var(--fg-muted)' }}
    >
      {children}
    </p>
  )
}
