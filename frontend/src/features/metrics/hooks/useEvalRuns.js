/** Hook for the eval harness: datasets, run history, and run polling. */
import { useCallback, useEffect, useState } from 'react'
import metricsService from '../services/metricsService'

// 3s while a run executes, against useMetrics' 30s. These are not window
// aggregations: a retrieval-only run over a small dataset finishes in
// seconds, and a stale "running" badge is precisely the failure this panel
// exists to avoid. Polling stops the moment the status is terminal.
const RUN_POLL_INTERVAL = 3000

const TERMINAL_STATUSES = ['completed', 'failed']

/** Whether a run is still executing. A missing run is not running. */
export function isRunning(run) {
  return Boolean(run?.run_id) && !TERMINAL_STATUSES.includes(run?.status)
}

/**
 * Load the tenant's golden sets and drive one run at a time.
 *
 * The panel is presentational; every fetch, poll and mutation lives here.
 */
export function useEvalRuns() {
  const [datasets, setDatasets] = useState([])
  const [datasetId, setDatasetId] = useState('')
  const [runs, setRuns] = useState([])
  const [run, setRun] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const loadDatasets = useCallback(async () => {
    setLoading(true)
    try {
      const response = await metricsService.listEvalDatasets()
      const list = response?.datasets || []
      setDatasets(list)
      setError(null)
      // Keep the current selection when it survived the reload, so deleting
      // some other dataset does not bounce the user to the first one.
      setDatasetId((current) =>
        current && list.some((entry) => entry.dataset_id === current)
          ? current
          : list[0]?.dataset_id || ''
      )
    } catch (err) {
      setError(err?.message || 'Failed to load eval datasets')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadRuns = useCallback(async (id) => {
    if (!id) {
      setRuns([])
      setRun(null)
      return
    }
    try {
      const response = await metricsService.listEvalRuns({ datasetId: id })
      const list = response?.runs || []
      setRuns(list)
      // The listing omits per-item rows, so the newest run is re-fetched in
      // full — that is where the drill-down comes from.
      if (list[0]?.run_id) {
        const detail = await metricsService.getEvalRun(list[0].run_id)
        setRun(detail?.run || null)
      } else {
        setRun(null)
      }
      setError(null)
    } catch (err) {
      setError(err?.message || 'Failed to load evaluation runs')
    }
  }, [])

  useEffect(() => {
    loadDatasets()
  }, [loadDatasets])

  useEffect(() => {
    loadRuns(datasetId)
  }, [datasetId, loadRuns])

  // Poll only while the run is executing. Keyed on the id and status rather
  // than the run object so a poll that changes nothing does not tear down
  // and rebuild the interval.
  const runId = run?.run_id
  const runStatus = run?.status
  useEffect(() => {
    if (!isRunning({ run_id: runId, status: runStatus })) return undefined

    const timer = setInterval(async () => {
      try {
        const detail = await metricsService.getEvalRun(runId)
        const next = detail?.run || null
        setRun(next)
        // A finished run changes the history the chart draws, so reload it
        // once — not on every tick.
        if (!isRunning(next)) loadRuns(datasetId)
      } catch {
        // A single failed poll is not a failed run. Keep polling; the run
        // document itself is the source of truth for terminal state.
      }
    }, RUN_POLL_INTERVAL)

    return () => clearInterval(timer)
  }, [runId, runStatus, datasetId, loadRuns])

  const startRun = useCallback(
    async (mode = 'retrieval') => {
      if (!datasetId) return
      setBusy(true)
      try {
        const response = await metricsService.startEvalRun(datasetId, mode)
        setRun(response?.run || null)
        setError(null)
      } catch (err) {
        setError(err?.message || 'Could not start the evaluation run')
      } finally {
        setBusy(false)
      }
    },
    [datasetId]
  )

  /**
   * Price a prospective run without starting it.
   *
   * Returns null on failure rather than throwing: an unavailable estimate
   * must not block a `retrieval` run, which costs nothing either way. The
   * panel refuses to start an `end_to_end` run without one.
   */
  const estimateRunCost = useCallback(async (itemCount, mode, model) => {
    try {
      return await metricsService.estimateEvalRunCost({ itemCount, mode, model })
    } catch (err) {
      setError(err?.message || 'Could not estimate the run cost')
      return null
    }
  }, [])

  const createDataset = useCallback(
    async (body) => {
      setBusy(true)
      try {
        const response = await metricsService.createEvalDataset(body)
        await loadDatasets()
        setDatasetId(response?.dataset?.dataset_id || '')
        setError(null)
        return true
      } catch (err) {
        // Surfaced by the modal rather than swallowed: the server's message
        // names the offending item, which is the only useful thing to show.
        setError(err?.message || 'Could not import the dataset')
        return false
      } finally {
        setBusy(false)
      }
    },
    [loadDatasets]
  )

  const deleteDataset = useCallback(
    async (id) => {
      setBusy(true)
      try {
        await metricsService.deleteEvalDataset(id)
        await loadDatasets()
        setError(null)
      } catch (err) {
        setError(err?.message || 'Could not delete the dataset')
      } finally {
        setBusy(false)
      }
    },
    [loadDatasets]
  )

  const refresh = useCallback(async () => {
    await loadDatasets()
    await loadRuns(datasetId)
  }, [loadDatasets, loadRuns, datasetId])

  return {
    datasets,
    datasetId,
    selectDataset: setDatasetId,
    runs,
    run,
    running: isRunning(run),
    loading,
    error,
    busy,
    startRun,
    estimateRunCost,
    createDataset,
    deleteDataset,
    refresh,
  }
}
