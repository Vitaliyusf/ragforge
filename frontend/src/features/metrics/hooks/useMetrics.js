/** Hook for polling one admin metrics section. */
import { useCallback, useEffect, useRef, useState } from 'react'
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
}

/**
 * Poll a single metrics section.
 *
 * Only the section named here is fetched — the tab must not pull all five
 * endpoints to render one panel.
 *
 * @param {string} section - 'overview' | 'latency' | 'retrieval' | 'quality' | 'pipeline'
 * @param {{window?: string, tenantId?: string}} params
 */
export function useMetrics(section, { window: windowRange, tenantId } = {}) {
  const [state, setState] = useState(INITIAL_STATE)
  const controllerRef = useRef(null)

  const fetchSection = useCallback(
    async ({ silent = false } = {}) => {
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

  useEffect(() => {
    fetchSection()

    // A dashboard left open in a background tab must not keep hitting the
    // gateway, so the tick skips while hidden and catches up on return.
    const interval = setInterval(() => {
      if (!document.hidden) fetchSection({ silent: true })
    }, POLL_INTERVAL)

    const handleVisibility = () => {
      if (!document.hidden) fetchSection({ silent: true })
    }
    document.addEventListener('visibilitychange', handleVisibility)

    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', handleVisibility)
      controllerRef.current?.abort()
    }
  }, [fetchSection])

  const refresh = useCallback(() => fetchSection(), [fetchSection])

  return { ...state, refresh }
}
