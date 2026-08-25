/** Admin metrics service — one method per /v1/metrics route. */
import { del, get, patch, post } from '@/lib/http/client'

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

  // ── Eval harness ────────────────────────────────────────────────────
  // Not windowed and not Prometheus-backed, so these return the rag payload
  // directly rather than the `{window, data, prometheus_available}` envelope
  // the five panel routes share.

  async listEvalDatasets() {
    return await get('/v1/metrics/eval/datasets')
  }

  async createEvalDataset({ name, description, items }) {
    return await post('/v1/metrics/eval/datasets', { name, description, items })
  }

  async updateEvalDataset(datasetId, body) {
    return await patch(`/v1/metrics/eval/datasets/${encodeURIComponent(datasetId)}`, body)
  }

  async deleteEvalDataset(datasetId) {
    return await del(`/v1/metrics/eval/datasets/${encodeURIComponent(datasetId)}`)
  }

  /** Returns as soon as the run is queued; poll `getEvalRun` for progress. */
  async startEvalRun(datasetId) {
    return await post('/v1/metrics/eval/runs', { dataset_id: datasetId })
  }

  async listEvalRuns({ datasetId, limit } = {}) {
    const params = new URLSearchParams()
    if (datasetId) params.set('dataset_id', datasetId)
    if (limit) params.set('limit', String(limit))
    const query = params.toString()
    return await get(`/v1/metrics/eval/runs${query ? `?${query}` : ''}`)
  }

  async getEvalRun(runId) {
    return await get(`/v1/metrics/eval/runs/${encodeURIComponent(runId)}`)
  }
}

export default new MetricsService()
