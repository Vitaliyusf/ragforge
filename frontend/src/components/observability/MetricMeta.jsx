'use client'

import { Clock, Database, Globe, HelpCircle } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import { cn } from '@/lib/utils'
import { DATA_STATE, METRIC_SCOPE } from '@/lib/observability/metricMeta'

/**
 * The trust contract, rendered.
 *
 * These are the only components allowed to say a figure's scope or age. A
 * panel that wrote its own wording would eventually disagree with another
 * panel about the same number, and the disagreement an operator cannot see is
 * the one that costs them an hour.
 */

const SCOPE_ICONS = {
  [METRIC_SCOPE.TENANT]: Database,
  [METRIC_SCOPE.PLATFORM]: Globe,
  [METRIC_SCOPE.UNKNOWN]: HelpCircle,
}

const SCOPE_VARIANTS = {
  [METRIC_SCOPE.TENANT]: 'outline',
  // Platform-wide is the one that misleads if it goes unread in a
  // tenant-scoped page, so it is the one that carries a colour.
  [METRIC_SCOPE.PLATFORM]: 'warning',
  [METRIC_SCOPE.UNKNOWN]: 'warning',
}

/**
 * Whose data this is: a tenant's, or the whole platform's.
 * @param {{scope: {scope: string, label: string, detail: ?string, title: string}}} props
 */
export function ScopeBadge({ scope, size = 'xs', className = '' }) {
  if (!scope) return null
  return (
    <Badge
      variant={SCOPE_VARIANTS[scope.scope] || 'outline'}
      size={size}
      icon={SCOPE_ICONS[scope.scope] || HelpCircle}
      title={scope.title}
      className={className}
    >
      {scope.detail ? `${scope.label} · ${scope.detail}` : scope.label}
    </Badge>
  )
}

const FRESHNESS_VARIANTS = {
  [DATA_STATE.DELAYED]: 'warning',
  [DATA_STATE.STALE]: 'danger',
  [DATA_STATE.UNAVAILABLE]: 'outline',
}

/**
 * How old the data is — shown only when that is news.
 *
 * A badge saying "up to date" on every panel is noise that trains the eye to
 * skip the place a real warning would appear.
 */
export function FreshnessBadge({ freshness, size = 'xs', className = '' }) {
  if (!freshness) return null
  const variant = FRESHNESS_VARIANTS[freshness.state]
  if (!variant) return null
  return (
    <Badge variant={variant} size={size} icon={Clock} className={className}>
      {freshness.label}
    </Badge>
  )
}

/**
 * Scope, range, sample count and freshness on one line.
 *
 * @param {{meta: object}} props `meta` comes from `describeMetric`.
 */
export function MetricTrustLine({ meta, className = '' }) {
  if (!meta) return null
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <ScopeBadge scope={meta.scope} />
      <span className="text-xs" style={{ color: 'var(--fg-soft)' }}>
        {meta.rangeLabel} · {meta.sampleLabel}
      </span>
      <FreshnessBadge freshness={meta.freshness} />
    </div>
  )
}

/**
 * Said on a widget the page-level filter does not reach.
 *
 * The window and tenant selectors sit above every panel, so a widget they do
 * not apply to has to say so where the widget is, not in a footnote.
 */
export function FilterScopeNote({ children, className = '' }) {
  return (
    <p
      className={cn('text-xs', className)}
      style={{ color: 'var(--fg-soft)' }}
    >
      {children}
    </p>
  )
}
