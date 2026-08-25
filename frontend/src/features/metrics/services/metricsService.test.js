/** Query-string construction and response passthrough for the metrics API. */
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import metricsService from './metricsService'

const API_BASE_URL = 'http://localhost:8000'

function envelope(overrides = {}) {
  return {
    window: '24h',
    tenant_id: 'tenant-1',
    generated_at: '2026-08-25T12:00:00+00:00',
    prometheus_available: true,
    prometheus_scope: 'all_tenants',
    data: { turns: 7 },
    ...overrides,
  }
}

describe('metricsService', () => {
  let requested

  beforeEach(() => {
    requested = []
    server.use(
      http.get(`${API_BASE_URL}/v1/metrics/:section`, ({ request, params }) => {
        requested.push({ section: params.section, url: new URL(request.url) })
        return HttpResponse.json(envelope())
      })
    )
  })

  it('sends the window and tenant as query parameters', async () => {
    await metricsService.getOverview({ window: '7d', tenantId: 'tenant-9' })

    const { url } = requested[0]
    expect(url.pathname).toBe('/v1/metrics/overview')
    expect(url.searchParams.get('window')).toBe('7d')
    expect(url.searchParams.get('tenant_id')).toBe('tenant-9')
  })

  it('omits tenant_id when it is empty', async () => {
    await metricsService.getOverview({ window: '1h', tenantId: '' })

    const { url } = requested[0]
    expect(url.searchParams.get('window')).toBe('1h')
    expect(url.searchParams.has('tenant_id')).toBe(false)
  })

  it('omits tenant_id when it is not supplied at all', async () => {
    await metricsService.getLatency({ window: '30d' })
    expect(requested[0].url.searchParams.has('tenant_id')).toBe(false)
  })

  it('sends no query string when called with no parameters', async () => {
    await metricsService.getQuality()
    expect(requested[0].url.search).toBe('')
  })

  it('returns the envelope unchanged', async () => {
    const result = await metricsService.getOverview({ window: '24h' })

    expect(result).toEqual(envelope())
    expect(result.prometheus_available).toBe(true)
    expect(result.data.turns).toBe(7)
  })

  it('routes each method to its own endpoint', async () => {
    await metricsService.getOverview({ window: '1h' })
    await metricsService.getLatency({ window: '1h' })
    await metricsService.getRetrieval({ window: '1h' })
    await metricsService.getQuality({ window: '1h' })
    await metricsService.getPipeline({ window: '1h' })

    expect(requested.map((entry) => entry.section)).toEqual([
      'overview',
      'latency',
      'retrieval',
      'quality',
      'pipeline',
    ])
  })
})
