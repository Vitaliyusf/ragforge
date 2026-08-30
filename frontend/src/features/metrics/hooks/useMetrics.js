/** Hook for polling one admin metrics section. */
import { useCallback, useEffect, useEffectEvent, useRef, useState } from 'react'
import metricsService from '../services/metricsService'

// 30s, not the 5s useHealth uses: these are aggregation queries over a
// window, not liveness pings, and they cost the gateway an RPC plus a
// concurrent batch of Prometheus reads.
const POLL_INTERVAL = 30000

const SECTION_FETCHERS = {
  overview: (params) => metricsService.getOverview(params),
  latency: (params) => metricsService.getLatency(params),
  retrieval: (params) => metricsService.getRetrieval(params),
  quality: (params) => metricsService.getQuality(params),
  pipeline: (params) => metricsService.getPipeline(params),
}

const INITIAL_STATE = {
  data: null,
  loading: true,
  error: null,
  promAvailable: true,
  lastUpdated: null,
  // Envelope metadata, kept rather than dropped: it is the only evidence the
  // UI has for whose data this is and how old it is. `tenantId` is the tenant
  // the response says it actually aggregated, never the one that was asked
  // for, so a panel cannot claim a tenant the backend did not read.
  tenantId: null,
  prometheusScope: null,
  generatedAt: null,
}

/**
 * Poll a single metrics section.
 *
 * Only the section named here is fetched — the tab must not pull all five
 * endpoints to render one panel.
 *
 * @param {?string} section - 'overview' | 'latency' | 'retrieval' | 'quality' |
 *   'pipeline', or null for a section that loads its own data.
 * @param {{window?: string, tenantId?: string}} params
 */
export function useMetrics(section, { window: windowRange, tenantId } = {}) {
  const [state, setState] = useState(INITIAL_STATE)
  const controllerRef = useRef(null)

  const fetchSection = useCallback(
    async ({ silent = false } = {}) => {
      // A standalone section (see METRICS_SECTIONS) owns its own loading.
      // Idling here is not an error: there is no windowed endpoint to call,
      // and reporting "unknown section" would put a spurious error banner
      // above a panel that is working perfectly.
      if (!section) {
        setState({ ...INITIAL_STATE, loading: false })
        return
      }

      const fetcher = SECTION_FETCHERS[section]
      if (!fetcher) {
        setState({ ...INITIAL_STATE, loading: false, error: `Unknown metrics section: ${section}` })
        return
      }

      // Abandon whatever is still in flight. Switching window mid-request
      // would otherwise let the older response land last and overwrite the
      // newer one.
      controllerRef.current?.abort()
      const controller = new AbortController()
      controllerRef.current = controller

      if (!silent) setState((prev) => ({ ...prev, loading: true }))

      try {
        const response = await fetcher({ window: windowRange, tenantId })
        if (controller.signal.aborted) return
        setState({
          data: response?.data ?? null,
          loading: false,
          error: null,
          promAvailable: response?.prometheus_available !== false,
          lastUpdated: response?.generated_at ? new Date(response.generated_at) : new Date(),
          tenantId: response?.tenant_id ?? null,
          prometheusScope: response?.prometheus_scope ?? null,
          // Null when the response carried no stamp: freshness is then
          // reported as unknown rather than as the moment it happened to
          // arrive here, which would always look current.
          generatedAt: response?.generated_at ?? null,
        })
      } catch (err) {
        if (controller.signal.aborted) return
        setState((prev) => ({
          ...prev,
          loading: false,
          error: err?.message || 'Failed to load metrics',
        }))
      }
    },
    [section, windowRange, tenantId]
  )

  // Visible-only refresh, always running the newest fetcher but never itself a
  // reason to resubscribe.
  const refreshIfVisible = useEffectEvent(() => {
    if (!document.hidden) fetchSection({ silent: true })
  })

  // Changing the section, window or tenant is a *reload*, so this Effect
  // re-runs and abandons the in-flight request.
  useEffect(() => {
    fetchSection()
    return () => controllerRef.current?.abort()
  }, [fetchSection])

  // The poll and the visibility listener are a *lifecycle*, so they are mounted
  // once. Previously they were rebuilt on every window/tenant change, which
  // detached and reattached the document listener and reset the 30s phase.
  // A dashboard left open in a background tab must not keep hitting the
  // gateway, so the tick skips while hidden and catches up on return.
  useEffect(() => {
    const onTick = () => refreshIfVisible()
    const interval = setInterval(onTick, POLL_INTERVAL)
    document.addEventListener('visibilitychange', onTick)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', onTick)
    }
  }, [])

  const refresh = useCallback(() => fetchSection(), [fetchSection])

  return { ...state, refresh }
}
