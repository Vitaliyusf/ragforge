'use client'

import { cn } from '@/lib/utils'

/**
 * Shared read-only data display primitives.
 *
 * These replace several near-identical local components that had grown up
 * independently across the features: DetailRow (FilesTab), MetaCard
 * (FileReviewDrawer), the audit-trail meta cells and the stat cells of the
 * chat Developer Inspector. MetaCard and the audit meta cell were identical
 * apart from their border radius.
 */

/** Inline `label: value`, for dense detail lists. */
export function DataRow({ label, value, mono = false, className = '' }) {
  return (
    <div className={cn('flex items-start gap-2 rounded-xl px-3 py-2 text-[13px]', className)}>
      <span className="shrink-0 font-medium text-text-secondary">{label}:</span>
      <span className={cn('min-w-0 break-all text-text-secondary', mono && 'font-mono')}>{value}</span>
    </div>
  )
}

/**
 * Stacked label/value in a bordered box.
 *
 * `reverse` puts the value above the label, which is how the trace panel
 * presents its counts; `valueClassName` lets a caller colour the value by
 * score without the primitive knowing anything about scoring.
 */
export function DataCell({
  label,
  value,
  mono = false,
  center = false,
  reverse = false,
  uppercaseLabel = true,
  valueClassName = '',
  className = '',
}) {
  const labelEl = (
    <div className={cn('text-xs text-text-muted', !reverse && uppercaseLabel && 'uppercase tracking-wide')}>
      {label}
    </div>
  )
  const valueEl = (
    <div
      className={cn(
        'break-all text-[15px] text-text-primary',
        reverse ? 'font-bold' : 'mt-1',
        mono && 'font-mono',
        valueClassName
      )}
    >
      {value ?? '-'}
    </div>
  )

  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-bg-elevated px-3 py-2',
        center && 'text-center',
        className
      )}
    >
      {reverse ? valueEl : labelEl}
      {reverse ? <div className="mt-0.5">{labelEl}</div> : valueEl}
    </div>
  )
}

/**
 * Labelled, scrollable preformatted block. Objects are JSON-stringified;
 * strings are rendered as-is.
 */
export function CodeBlock({
  label,
  content,
  emptyText = 'Not available',
  hideWhenEmpty = false,
  className = '',
}) {
  const text = typeof content === 'string'
    ? content
    : content != null
      ? JSON.stringify(content, null, 2)
      : ''

  if (hideWhenEmpty && !text) return null

  return (
    <div className={className}>
      {label ? <div className="mb-1 text-[13px] font-medium text-text-muted">{label}</div> : null}
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border bg-bg-elevated p-3 text-[13px] text-text-secondary">
        {text || emptyText}
      </pre>
    </div>
  )
}
