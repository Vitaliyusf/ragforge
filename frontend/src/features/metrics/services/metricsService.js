/** Admin metrics service — one method per /v1/metrics route. */
import { get } from '@/lib/http/client'

/**
 * Build the shared query string. `tenant_id` is omitted when empty so the
 * gateway falls back to the caller's own tenant rather than receiving a
 * blank value it would have to interpret.
 */
function buildQuery({ window, tenantId } = {}) {
  const params = new URLSearchParams()
  if (window) params.set('window', window)
  if (tenantId) params.set('tenant_id', tenantId)
  const query = params.toString()
  return query ? `?${query}` : ''
}

class MetricsService {
  async getOverview(params) {
    return await get(`/v1/metrics/overview${buildQuery(params)}`)
  }

  async getLatency(params) {
    return await get(`/v1/metrics/latency${buildQuery(params)}`)
  }

  async getRetrieval(params) {
    return await get(`/v1/metrics/retrieval${buildQuery(params)}`)
  }

  async getQuality(params) {
    return await get(`/v1/metrics/quality${buildQuery(params)}`)
  }

  async getPipeline(params) {
    return await get(`/v1/metrics/pipeline${buildQuery(params)}`)
  }
}

export default new MetricsService()
