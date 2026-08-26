/** Full benchmark state, including abortable, visibility-aware polling. */
import { useCallback, useEffect, useRef, useState } from 'react'
import metricsService from '../services/metricsService'

export const BENCHMARK_POLL_INTERVAL = 3000
const TERMINAL = new Set(['completed', 'partial', 'failed', 'interrupted'])
export const isBenchmarkRunning = (benchmark) => Boolean(benchmark?.benchmark_id) && !TERMINAL.has(benchmark.status)

export function useBenchmarkRuns(datasetId) {
  const [benchmark, setBenchmark] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const controllerRef = useRef(null)

  const load = useCallback(async (id, signal) => {
    if (!id) return null
    const response = await metricsService.getBenchmarkRun(id, { signal })
    const next = response?.benchmark || null
    setBenchmark(next)
    return next
  }, [])

  useEffect(() => () => controllerRef.current?.abort(), [])

  // The server is the source of truth.  Restoring from the dataset list also
  // makes a fresh browser session behave exactly like an in-app remount.
  useEffect(() => {
    if (!datasetId) {
      setBenchmark(null)
      return undefined
    }
    const controller = new AbortController()
    controllerRef.current?.abort()
    controllerRef.current = controller
    setBenchmark(null)
    setError(null)
    ;(async () => {
      try {
        const response = await metricsService.listBenchmarkRuns({ datasetId, signal: controller.signal })
        const runs = response?.benchmarks || response?.runs || []
        const restored = runs.find(isBenchmarkRunning) || runs[0] || null
        if (!controller.signal.aborted) setBenchmark(restored)
      } catch (err) {
        if (err?.name !== 'AbortError' && !controller.signal.aborted) setError(err?.message || 'Could not restore benchmark history')
      }
    })()
    return () => controller.abort()
  }, [datasetId])

  useEffect(() => {
    if (!isBenchmarkRunning(benchmark) || document.visibilityState === 'hidden') return undefined
    let controller = new AbortController()
    controllerRef.current?.abort()
    controllerRef.current = controller
    const poll = async () => {
      try { await load(benchmark.benchmark_id, controller.signal) }
      catch (err) { if (err?.name !== 'AbortError') setError(err?.message || 'Could not update benchmark progress') }
    }
    const timer = setInterval(poll, BENCHMARK_POLL_INTERVAL)
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        controller.abort()
      } else {
        // A fresh controller: reusing the one aborted above would leave
        // every poll after a hide/show cycle hitting fetch with an
        // already-aborted signal, silently short-circuiting forever.
        controller = new AbortController()
        controllerRef.current = controller
        poll()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => { clearInterval(timer); controller.abort(); document.removeEventListener('visibilitychange', onVisibility) }
  }, [benchmark?.benchmark_id, benchmark?.status, load])

  const start = useCallback(async (phases) => {
    if (!datasetId) return null
    controllerRef.current?.abort()
    setBusy(true)
    try {
      const response = await metricsService.startBenchmarkRun(datasetId, phases)
      const next = response?.benchmark || null
      setBenchmark(next)
      setError(null)
      return next
    } catch (err) { setError(err?.message || 'Could not start the benchmark'); return null }
    finally { setBusy(false) }
  }, [datasetId])

  const download = useCallback(async () => {
    if (!benchmark?.benchmark_id) return
    setBusy(true)
    try {
      const { blob, filename } = await metricsService.downloadBenchmark(benchmark.benchmark_id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = filename; link.click()
      URL.revokeObjectURL(url)
    } catch (err) { setError(err?.message || 'Could not download the benchmark archive') }
    finally { setBusy(false) }
  }, [benchmark?.benchmark_id])

  return { benchmark, error, busy, start, download }
}
