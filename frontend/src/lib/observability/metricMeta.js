/**
 * The metrics trust contract, in one place.
 *
 * Every number on an observability surface has to be able to answer the same
 * questions before it is worth reading: what it measures, over how many
 * samples, for whom, over what range, from which store, how old it is, and
 * whether it is a real reading at all. Before this module each panel answered
 * some of those in prose of its own and dropped the rest, so the most
 * dangerous case — a platform-wide Prometheus figure sitting in a
 * tenant-scoped panel — was invisible.
 *
 * The rules that shape it:
 *
 * - **Scope is never inferred.** It is derived from what the response
 *   actually reported (`tenant_id`, `prometheus_scope`). A response that
 *   named no tenant produces `UNKNOWN`, not the caller's own tenant.
 * - **Absent is not zero.** A missing sample count is `null` and reads as
 *   "not reported"; it never becomes a confident 0.
 * - **`—` is not a state.** Every empty cell resolves to one of the states in
 *   {@link DATA_STATE}, which say which kind of nothing this is.
 */

import { formatCompactAge } from '@/lib/formatting/datetime'
import { DEFAULT_LOCALE } from '@/i18n/locale'
import { translate } from '@/i18n/translate'

/**
 * English resolution for callers with no locale to hand.
 *
 * This module is pure and is imported by hooks as well as by components, so
 * the translator is injected rather than read from React context. Every
 * describe* function takes an optional `t` and falls back to English, which
 * is also what keeps its tests locale-free.
 */
const defaultTranslate = (key, variables) => translate(DEFAULT_LOCALE, key, variables)

/** Which store a figure came from. They fail, and are scoped, differently. */
export const METRIC_SOURCE = Object.freeze({
  /** Prometheus: platform-wide, and can be down while everything else works. */
  PROMETHEUS: 'prometheus',
  /** The per-turn MongoDB store behind rag/files: tenant-scoped, always up. */
  METRICS_STORE: 'metrics_store',
})

export const METRIC_SCOPE = Object.freeze({
  TENANT: 'tenant',
  PLATFORM: 'platform',
  UNKNOWN: 'unknown',
})

/**
 * What kind of nothing — or something — a widget is showing.
 *
 * `NO_DATA` and `UNAVAILABLE` are the pair the old single `—` conflated: one
 * means the window was quiet, the other means nobody answered.
 */
export const DATA_STATE = Object.freeze({
  LOADING: 'loading',
  OK: 'ok',
  NO_DATA: 'no_data',
  DELAYED: 'delayed',
  STALE: 'stale',
  PARTIAL: 'partial',
  UNAVAILABLE: 'unavailable',
})

/**
 * Freshness thresholds, in milliseconds.
 *
 * The defaults are read against the 30s metrics poll: one missed refresh is
 * noise, three is a signal, ten means the number on screen is history. A
 * surface that polls at a different cadence passes its own.
 */
export const FRESHNESS_THRESHOLDS = Object.freeze({
  delayedAfterMs: 90_000,
  staleAfterMs: 300_000,
})

const SCOPE_LABEL_KEYS = Object.freeze({
  [METRIC_SCOPE.TENANT]: 'meta.scope.tenant',
  [METRIC_SCOPE.PLATFORM]: 'meta.scope.platform',
  [METRIC_SCOPE.UNKNOWN]: 'meta.scope.unknown',
})

/** Shown beside any figure Prometheus supplies: these carry no tenant label. */
export const PLATFORM_SCOPE_NOTE = defaultTranslate('meta.platformScopeNote')

/** Shown when a response named no tenant, so nothing may claim one. */
export const UNKNOWN_SCOPE_NOTE = defaultTranslate('meta.unknownScopeNote')

/**
 * Describe the scope of one figure.
 *
 * @param {object} options
 * @param {string} options.source one of {@link METRIC_SOURCE}
 * @param {?string} [options.tenantId] the tenant the response said it read
 * @param {?string} [options.prometheusScope] the envelope's `prometheus_scope`
 * @returns {{scope: string, label: string, detail: ?string, title: string}}
 */
export function describeScope({ source, tenantId, prometheusScope, t = defaultTranslate } = {}) {
  if (source === METRIC_SOURCE.PROMETHEUS) {
    // `all_tenants` is the only scope phase-1 series carry. Anything else is
    // a contract the frontend has not been taught, and guessing "tenant"
    // would be the exact mislabelling this module exists to prevent.
    const perTenant = prometheusScope === METRIC_SCOPE.TENANT
    if (!perTenant) {
      return {
        scope: METRIC_SCOPE.PLATFORM,
        label: t(SCOPE_LABEL_KEYS[METRIC_SCOPE.PLATFORM]),
        detail: t('meta.allTenants'),
        title: t('meta.platformScopeNote'),
      }
    }
  }

  if (!tenantId) {
    return {
      scope: METRIC_SCOPE.UNKNOWN,
      label: t(SCOPE_LABEL_KEYS[METRIC_SCOPE.UNKNOWN]),
      detail: null,
      title: t('meta.unknownScopeNote'),
    }
  }

  return {
    scope: METRIC_SCOPE.TENANT,
    label: t(SCOPE_LABEL_KEYS[METRIC_SCOPE.TENANT]),
    // The tenant id itself is a backend identifier, never translated.
    detail: tenantId,
    title: t('meta.scopedToTenant', { tenant: tenantId }),
  }
}

/**
 * How old the data on screen is.
 *
 * @param {string|number|Date|null} generatedAt when the response was built
 * @param {object} [options]
 * @param {number} [options.now] injectable clock, so tests do not race it
 * @param {number} [options.delayedAfterMs]
 * @param {number} [options.staleAfterMs]
 * @returns {{state: string, ageMs: ?number, label: string}} `state` is
 *   `ok`, `delayed`, `stale`, or `unavailable` when nothing datable arrived.
 */
export function describeFreshness(generatedAt, options = {}) {
  const {
    now = Date.now(),
    delayedAfterMs = FRESHNESS_THRESHOLDS.delayedAfterMs,
    staleAfterMs = FRESHNESS_THRESHOLDS.staleAfterMs,
    t = defaultTranslate,
  } = options

  const parsed = generatedAt == null || generatedAt === '' ? null : new Date(generatedAt)
  if (!parsed || Number.isNaN(parsed.getTime())) {
    return { state: DATA_STATE.UNAVAILABLE, ageMs: null, label: t('meta.freshnessUnknown') }
  }

  // A response stamped in the future is a clock skew between two machines,
  // not data from the future. It reads as current rather than as an age.
  const ageMs = Math.max(0, now - parsed.getTime())
  const age = formatCompactAge(ageMs)

  if (ageMs >= staleAfterMs) {
    return {
      state: DATA_STATE.STALE,
      ageMs,
      label: age ? t('meta.dataStaleAge', { age }) : t('meta.dataStale'),
    }
  }
  if (ageMs >= delayedAfterMs) {
    return {
      state: DATA_STATE.DELAYED,
      ageMs,
      label: age ? t('meta.dataDelayedAge', { age }) : t('meta.dataDelayed'),
    }
  }
  return { state: DATA_STATE.OK, ageMs, label: t('meta.upToDate') }
}

/**
 * Resolve the one state a widget should render.
 *
 * Order matters and is the order an operator needs: still arriving, then
 * broken, then incomplete, then empty, then merely old, then fine. A widget
 * whose store is down must never fall through to "no data in this window",
 * which reads as a quiet system rather than a blind one.
 *
 * @param {object} options
 * @param {boolean} [options.loading] a first load, with nothing to show yet
 * @param {?string} [options.error]
 * @param {boolean} [options.sourceAvailable] false when the store is down
 * @param {boolean} [options.partial] some sources answered and some did not
 * @param {?number} [options.sampleCount] null when the count is not reported
 * @param {?string} [options.freshness] a state from {@link describeFreshness}
 * @returns {string} one of {@link DATA_STATE}
 */
export function resolveDataState({
  loading = false,
  error = null,
  sourceAvailable = true,
  partial = false,
  sampleCount = null,
  freshness = null,
} = {}) {
  if (loading) return DATA_STATE.LOADING
  if (error || !sourceAvailable) return DATA_STATE.UNAVAILABLE
  if (partial) return DATA_STATE.PARTIAL
  if (sampleCount === 0) return DATA_STATE.NO_DATA
  if (freshness === DATA_STATE.STALE) return DATA_STATE.STALE
  if (freshness === DATA_STATE.DELAYED) return DATA_STATE.DELAYED
  return DATA_STATE.OK
}

/**
 * Say how many samples a figure is averaged over.
 *
 * @param {?number} count
 * @param {string} [noun] singular noun for one sample
 * @returns {string}
 */
export function describeSamples(count, noun = 'sample', t = defaultTranslate) {
  if (count == null || !Number.isFinite(Number(count))) return t('meta.sampleCountUnknown')
  const numeric = Number(count)
  // A labelled count rather than a pluralised noun: Hebrew has no clean
  // equivalent of "1 turn / 2 turns", and the phrasing works for both.
  const nounText = t(`meta.sampleNoun.${noun}`)
  if (numeric === 0) return t('meta.noSamples', { noun: nounText })
  return t('meta.sampleCount', { count: numeric.toLocaleString(), noun: nounText })
}

/** Human phrasing for the selected window, used wherever a range is stated. */
export const TIME_RANGE_LABEL_KEYS = Object.freeze({
  '1h': 'meta.range.1h',
  '24h': 'meta.range.24h',
  '7d': 'meta.range.7d',
  '30d': 'meta.range.30d',
})

export function describeTimeRange(window, t = defaultTranslate) {
  if (!window) return t('meta.rangeNotReported')
  // A window the frontend has not been taught is shown verbatim rather
  // than guessed at — it is the backend's own spelling.
  const key = TIME_RANGE_LABEL_KEYS[window]
  return key ? t(key) : String(window)
}

/**
 * The whole contract for one figure, assembled once.
 *
 * Panels take the pieces they have room for; the point is that they all take
 * them from here, so two surfaces cannot describe the same number two ways.
 *
 * @returns {{scope: object, freshness: object, state: string, source: string,
 *   sampleLabel: string, rangeLabel: string, summary: string}}
 */
export function describeMetric({
  source = METRIC_SOURCE.METRICS_STORE,
  tenantId = null,
  prometheusScope = null,
  generatedAt = null,
  window = null,
  sampleCount = null,
  sampleNoun = 'sample',
  loading = false,
  error = null,
  sourceAvailable = true,
  partial = false,
  now,
  t = defaultTranslate,
} = {}) {
  const scope = describeScope({ source, tenantId, prometheusScope, t })
  const freshness = describeFreshness(generatedAt, now == null ? { t } : { now, t })
  const state = resolveDataState({
    loading,
    error,
    sourceAvailable,
    partial,
    sampleCount,
    freshness: freshness.state,
  })
  const sampleLabel = describeSamples(sampleCount, sampleNoun, t)
  const rangeLabel = describeTimeRange(window, t)
  const scopeText = scope.detail ? `${scope.label} · ${scope.detail}` : scope.label

  return {
    scope,
    freshness,
    state,
    source,
    sampleLabel,
    rangeLabel,
    summary: `${scopeText} · ${rangeLabel} · ${sampleLabel}`,
  }
}
