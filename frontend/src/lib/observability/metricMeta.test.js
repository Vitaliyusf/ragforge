/**
 * OBS-UX-01 — the metrics trust contract.
 *
 * The failure this file exists to prevent is a platform-wide number reading
 * as one tenant's, and its quieter cousin: an empty cell that could equally
 * mean "quiet window" or "monitoring is down".
 */
import { describe, expect, it } from 'vitest'

import {
  DATA_STATE,
  METRIC_SCOPE,
  METRIC_SOURCE,
  describeFreshness,
  describeMetric,
  describeSamples,
  describeScope,
  describeTimeRange,
  resolveDataState,
} from './metricMeta'

describe('describeScope', () => {
  it('reports a Prometheus figure as global even when a tenant was read', () => {
    const scope = describeScope({
      source: METRIC_SOURCE.PROMETHEUS,
      tenantId: 'acme',
      prometheusScope: 'all_tenants',
    })

    expect(scope.scope).toBe(METRIC_SCOPE.PLATFORM)
    expect(scope.detail).toBe('all tenants')
    expect(scope.title).toMatch(/no tenant label/i)
  })

  it('names the tenant a stored figure was actually aggregated for', () => {
    const scope = describeScope({ source: METRIC_SOURCE.METRICS_STORE, tenantId: 'acme' })

    expect(scope.scope).toBe(METRIC_SCOPE.TENANT)
    expect(scope.detail).toBe('acme')
  })

  it('refuses to claim a tenant the response never named', () => {
    const scope = describeScope({ source: METRIC_SOURCE.METRICS_STORE, tenantId: null })

    expect(scope.scope).toBe(METRIC_SCOPE.UNKNOWN)
    expect(scope.detail).toBeNull()
  })
})

describe('describeFreshness', () => {
  const now = Date.parse('2026-01-01T12:00:00Z')

  it('says nothing is wrong while the data is current', () => {
    const fresh = describeFreshness('2026-01-01T11:59:50Z', { now })
    expect(fresh.state).toBe(DATA_STATE.OK)
  })

  it('names the delay once a refresh has been missed', () => {
    const delayed = describeFreshness('2026-01-01T11:56:00Z', { now })
    expect(delayed.state).toBe(DATA_STATE.DELAYED)
    expect(delayed.label).toBe('Data delayed 4m')
  })

  it('escalates to stale rather than quietly ageing', () => {
    const stale = describeFreshness('2026-01-01T11:40:00Z', { now })
    expect(stale.state).toBe(DATA_STATE.STALE)
    expect(stale.label).toMatch(/20m/)
  })

  it('reports an unstamped response as unknown, not as current', () => {
    expect(describeFreshness(null, { now }).state).toBe(DATA_STATE.UNAVAILABLE)
    expect(describeFreshness('not a date', { now }).state).toBe(DATA_STATE.UNAVAILABLE)
  })

  it('treats a clock-skewed future stamp as current rather than negative', () => {
    const skewed = describeFreshness('2026-01-01T12:05:00Z', { now })
    expect(skewed.state).toBe(DATA_STATE.OK)
    expect(skewed.ageMs).toBe(0)
  })
})

describe('resolveDataState', () => {
  it('reports an unreachable store as unavailable, never as an empty window', () => {
    expect(resolveDataState({ sourceAvailable: false, sampleCount: 0 })).toBe(
      DATA_STATE.UNAVAILABLE
    )
  })

  it('distinguishes a quiet window from a broken one', () => {
    expect(resolveDataState({ sampleCount: 0 })).toBe(DATA_STATE.NO_DATA)
  })

  it('does not turn an unreported sample count into an empty window', () => {
    expect(resolveDataState({ sampleCount: null })).toBe(DATA_STATE.OK)
  })

  it('prefers partial over the freshness of the half that answered', () => {
    expect(resolveDataState({ partial: true, freshness: DATA_STATE.STALE })).toBe(
      DATA_STATE.PARTIAL
    )
  })

  it('carries freshness through when nothing louder is wrong', () => {
    expect(resolveDataState({ sampleCount: 12, freshness: DATA_STATE.DELAYED })).toBe(
      DATA_STATE.DELAYED
    )
  })
})

describe('describeSamples', () => {
  it('separates "none" from "not reported"', () => {
    expect(describeSamples(0, 'turn')).toBe('No turns in this range')
    expect(describeSamples(null, 'turn')).toBe('Sample count not reported')
  })

  it("counts in the caller's own noun", () => {
    expect(describeSamples(1, 'turn')).toBe('1 turn')
    expect(describeSamples(2400, 'turn')).toMatch(/turns$/)
  })
})

describe('describeTimeRange', () => {
  it('says the range is unreported rather than inventing one', () => {
    expect(describeTimeRange(null)).toBe('range not reported')
  })

  it('passes an unknown window through instead of hiding it', () => {
    expect(describeTimeRange('90d')).toBe('90d')
  })
})

describe('describeMetric', () => {
  it('states scope, range and denominator in one line', () => {
    const meta = describeMetric({
      source: METRIC_SOURCE.METRICS_STORE,
      tenantId: 'acme',
      generatedAt: '2026-01-01T12:00:00Z',
      window: '24h',
      sampleCount: 1200,
      sampleNoun: 'turn',
      now: Date.parse('2026-01-01T12:00:10Z'),
    })

    expect(meta.summary).toBe('Tenant · acme · last 24 hours · 1,200 turns')
    expect(meta.state).toBe(DATA_STATE.OK)
  })
})
