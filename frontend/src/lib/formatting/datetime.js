/**
 * Date and time formatting for display.
 *
 * Every formatter takes the interface locale as its last argument and defaults
 * to English. Two things follow from that:
 *
 *   1. The BCP-47 tag handed to `Intl` is derived here, once — `he` becomes
 *      `he-IL`, `en` becomes `en-US` — so no call site has to know that the
 *      interface locale and the formatting locale are spelled differently.
 *   2. Month and weekday names are never translated by hand. `Intl` already
 *      knows that August is "באוג׳" in Hebrew, and a hand-rolled table would
 *      be one more thing to keep in sync with the dictionary.
 *
 * Server timestamps are never altered; only their presentation changes.
 */

import { DEFAULT_LOCALE } from '@/i18n/locale'
import { translate } from '@/i18n/translate'

/**
 * Interface locale → the tag `Intl` should format with.
 *
 * Hebrew is pinned to `he-IL` rather than bare `he` so the 24-hour clock and
 * the day-month order come out the way a Hebrew reader expects; English is
 * pinned to `en-US`, which is the behaviour these surfaces already had when
 * they passed `undefined` and inherited the browser's default in development.
 */
const INTL_LOCALES = Object.freeze({
  en: 'en-US',
  he: 'he-IL',
})

/**
 * @param {string} [locale] an interface locale (`en` | `he`)
 * @returns {string} the BCP-47 tag to format with
 */
export function intlLocale(locale) {
  return INTL_LOCALES[locale] || INTL_LOCALES[DEFAULT_LOCALE]
}

/**
 * Format a message timestamp for display ("11:02 PM", "23:02").
 *
 * `hour12` is left to the locale rather than forced: Hebrew reads a 24-hour
 * clock, and an `11:02 PM` inside an RTL line is both wrong and awkward.
 *
 * @param {string|Date|null} timestamp
 * @param {string} [locale]
 * @returns {string}
 */
export function formatMessageTime(timestamp, locale = DEFAULT_LOCALE) {
  if (!timestamp) return ''
  try {
    const date = new Date(timestamp)
    if (isNaN(date.getTime())) return ''
    const diffMs = new Date() - date
    if (diffMs >= 0 && diffMs < 60_000) return translate(locale, 'time.justNow')
    return date.toLocaleTimeString(intlLocale(locale), {
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

/**
 * Format a date for the chat list ("Today", "Yesterday", "Jan 15", "28 באוג׳").
 * @param {string|Date} dateStr
 * @param {string} [locale]
 * @returns {string}
 */
export function formatChatDate(dateStr, locale = DEFAULT_LOCALE) {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return ''
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === today.toDateString()) return translate(locale, 'time.today')
    if (date.toDateString() === yesterday.toDateString()) {
      return translate(locale, 'time.yesterday')
    }
    return date.toLocaleDateString(intlLocale(locale), { month: 'short', day: 'numeric' })
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
 * @param {string} [locale]
 * @returns {string}
 */
export function formatAbsoluteDateTime(value, locale = DEFAULT_LOCALE) {
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
    return date.toLocaleString(intlLocale(locale), {
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
 *
 * Deliberately *not* localized. A latency is a technical measurement that an
 * operator reads next to a threshold and often copies; swapping its decimal
 * separator per locale would make two readings of the same number look like
 * two different numbers.
 *
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
 * The unit suffixes are single technical letters and stay as they are; the
 * *phrasing* around them is what `formatRelativeTime` localizes.
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
 * Format a timestamp as a compact age ("20s ago", "לפני 4m").
 *
 * Built for a dense table column, where an absolute date would cost more
 * width than it earns. Anything older than a month falls back to a date, and
 * an unparseable value returns `null` rather than a guess.
 *
 * @param {string|number|Date|null} value
 * @param {Date} [now] injectable clock, so tests do not race the wall clock
 * @param {string} [locale]
 * @returns {string|null}
 */
export function formatRelativeTime(value, now = new Date(), locale = DEFAULT_LOCALE) {
  if (value == null || value === '') return null
  const date = new Date(value)
  if (isNaN(date.getTime())) return null

  const elapsed = now.getTime() - date.getTime()
  if (elapsed < 0) return translate(locale, 'time.justNowLower')
  if (elapsed < 5000) return translate(locale, 'time.justNowLower')

  const age = formatCompactAge(elapsed)
  if (age) return translate(locale, 'time.ago', { age })
  return date.toLocaleDateString(intlLocale(locale), {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
