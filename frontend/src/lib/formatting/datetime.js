/** Date and time formatting for display. */

/**
 * Format a message timestamp for display (e.g. "2:30 PM").
 * Handles ISO strings, Date objects and locale time strings, and reports
 * "Just now" for anything inside the last minute.
 * @param {string|Date|null} timestamp
 * @returns {string}
 */
export function formatMessageTime(timestamp) {
  if (!timestamp) return ''
  try {
    const date = new Date(timestamp)
    if (isNaN(date.getTime())) return ''
    const diffMs = new Date() - date
    if (diffMs >= 0 && diffMs < 60_000) return 'Just now'
    return date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    })
  } catch {
    return ''
  }
}

/**
 * Format a date for the chat list (e.g. "Today", "Yesterday", "Jan 15").
 * @param {string|Date} dateStr
 * @returns {string}
 */
export function formatChatDate(dateStr) {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return ''
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === today.toDateString()) return 'Today'
    if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

/**
 * Format any timestamp the backend might hand over as a human date and time.
 *
 * Accepts ISO strings, `Date` objects, and raw epoch numbers in either seconds
 * or milliseconds — the inspector must never surface `1774310400` to a reader.
 * @param {string|number|Date|null} value
 * @returns {string}
 */
export function formatAbsoluteDateTime(value) {
  if (value == null || value === '') return ''
  try {
    // Epoch seconds and epoch milliseconds are told apart by magnitude: any
    // plausible second-precision timestamp is far below the ms threshold.
    const numeric = typeof value === 'number'
      ? value
      : (typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : null)
    const date = numeric == null
      ? new Date(value)
      : new Date(numeric < 1e11 ? numeric * 1000 : numeric)
    if (isNaN(date.getTime())) return ''
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

/**
 * Format a millisecond duration for display ("820 ms", "3.4 s").
 * @param {number|null} ms
 * @returns {string|null} `null` when the duration was never measured.
 */
export function formatDuration(ms) {
  if (!Number.isFinite(ms)) return null
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

const RELATIVE_UNITS = [
  { limit: 60_000, divisor: 1000, suffix: 's' },
  { limit: 3_600_000, divisor: 60_000, suffix: 'm' },
  { limit: 86_400_000, divisor: 3_600_000, suffix: 'h' },
  { limit: 2_592_000_000, divisor: 86_400_000, suffix: 'd' },
]

/**
 * Format an elapsed span as a bare compact age ("20s", "4m", "3d").
 *
 * No "ago": the caller supplies whatever phrasing its surface needs, which is
 * why the observability surfaces can say "delayed 4m" without a second copy
 * of these unit thresholds. Anything a month or older returns `null` — at
 * that distance a duration says less than a date.
 *
 * @param {number} elapsedMs
 * @returns {string|null}
 */
export function formatCompactAge(elapsedMs) {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return null
  for (const { limit, divisor, suffix } of RELATIVE_UNITS) {
    if (elapsedMs < limit) return `${Math.floor(elapsedMs / divisor)}${suffix}`
  }
  return null
}

/**
 * Format a timestamp as a compact age ("20s ago", "4m ago", "3d ago").
 *
 * Built for a dense table column, where an absolute date would cost more
 * width than it earns. Anything older than a month falls back to a date, and
 * an unparseable value returns `null` rather than a guess.
 *
 * @param {string|number|Date|null} value
 * @param {Date} [now] injectable clock, so tests do not race the wall clock
 * @returns {string|null}
 */
export function formatRelativeTime(value, now = new Date()) {
  if (value == null || value === '') return null
  const date = new Date(value)
  if (isNaN(date.getTime())) return null

  const elapsed = now.getTime() - date.getTime()
  if (elapsed < 0) return 'just now'
  if (elapsed < 5000) return 'just now'

  const age = formatCompactAge(elapsed)
  if (age) return `${age} ago`
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
