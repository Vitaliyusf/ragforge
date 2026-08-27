'use client'

/**
 * The single owner of benchmark truth for the navigation.
 *
 * The Eval page already polls the benchmark it is showing. Duplicating that
 * poll here would double the request rate against the very service whose
 * performance benchmarks are being measured, so this provider does the
 * opposite: while the Eval page is mounted it simply relays what the page
 * publishes, and it starts polling only once the page unmounts and a run is
 * still executing on the server.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import metricsService from '@/features/metrics/services/metricsService'
import { PROFILES_BY_ID, PHASE_SHORT_LABELS } from '@/features/eval/evalProfiles'
import { ACTIVITY_FEATURES, IDLE_ACTIVITY, isActiveState, mapBenchmarkStatus } from '../activityModel'
import { useActivity, useLiveActivitySource } from '../ActivityContext'

/**
 * 5s, and only while a run is known to be executing with no Eval page
 * mounted. The page's own 3s poll is the interactive one; the nav only has
 * to notice that a run ended.
 */
export const NAV_EVAL_POLL_INTERVAL = 5000

/** How many runs the one restore call reads on app start. */
export const EVAL_RESTORE_LIMIT = 5

const EvalActivityContext = createContext(null)

/** The item counter of the phase that is executing, else the phase counter. */
function benchmarkProgress(benchmark) {
  const progress = benchmark?.progress || {}
  const phases = Array.isArray(benchmark?.phases) ? benchmark.phases : []
  const active = phases.find((phase) => phase.status === 'running')
  const items = active?.item_progress || {}
  const perPhase = Number(progress.items_per_phase ?? 0)
  if (perPhase > 0 && Number.isFinite(Number(items.items_completed))) {
    return { completed: Number(items.items_completed), total: perPhase }
  }
  const total = Number(progress.executable_phases ?? progress.total_phases ?? 0)
  if (total > 0) return { completed: Number(progress.completed_phases ?? 0), total }
  return null
}

/** The run's own profile name, or the phase being executed. Never an ETA. */
function benchmarkLabel(benchmark) {
  const phases = Array.isArray(benchmark?.phases) ? benchmark.phases : []
  const active = phases.find((phase) => phase.status === 'running')
  if (active?.name && PHASE_SHORT_LABELS[active.name]) return PHASE_SHORT_LABELS[active.name]
  return PROFILES_BY_ID[benchmark?.profile]?.label || benchmark?.profile || undefined
}

export function benchmarkActivity(benchmark) {
  if (!benchmark?.benchmark_id) return { ...IDLE_ACTIVITY }
  return {
    state: mapBenchmarkStatus(benchmark.status),
    label: benchmarkLabel(benchmark),
    progress: benchmarkProgress(benchmark),
    startedAt: benchmark.started_at || null,
    completedAt: benchmark.finished_at || benchmark.completed_at || null,
  }
}

const isRunningBenchmark = (benchmark) => isActiveState(mapBenchmarkStatus(benchmark?.status))

export function EvalActivityProvider({ children, enabled = true }) {
  const { publish, hasLiveSource, liveVersion } = useActivity()
  const [benchmark, setBenchmark] = useState(null)

  const track = useCallback((next) => {
    setBenchmark((current) => {
      // A page publishing an older, unrelated run must not replace a run
      // that is still executing in the background.
      if (!next?.benchmark_id) return current
      if (current?.benchmark_id === next.benchmark_id) return next
      if (isRunningBenchmark(current) && !isRunningBenchmark(next)) return current
      return next
    })
  }, [])

  // One bounded restore on app start: a browser reload must not lose a run
  // that is still executing on the server. Terminal runs are deliberately
  // not restored — a green dot from yesterday is noise, not news.
  useEffect(() => {
    if (!enabled) return undefined
    const controller = new AbortController()
    ;(async () => {
      try {
        const response = await metricsService.listBenchmarkRuns({
          limit: EVAL_RESTORE_LIMIT,
          signal: controller.signal,
        })
        const runs = response?.benchmarks || response?.runs || []
        const active = runs.find(isRunningBenchmark)
        if (active && !controller.signal.aborted) track(active)
      } catch {
        // The nav is decoration over server truth. A failed restore leaves
        // it idle rather than inventing a state.
      }
    })()
    return () => controller.abort()
  }, [enabled, track])

  const benchmarkId = benchmark?.benchmark_id
  const running = isRunningBenchmark(benchmark)
  const pageOwnsPolling = hasLiveSource(ACTIVITY_FEATURES.EVAL)

  useEffect(() => {
    if (!enabled || !running || !benchmarkId || pageOwnsPolling) return undefined
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return undefined
    let controller = new AbortController()
    const poll = async () => {
      try {
        const response = await metricsService.getBenchmarkRun(benchmarkId, { signal: controller.signal })
        if (response?.benchmark) track(response.benchmark)
      } catch {
        // Keep polling: one failed request is not a finished run.
      }
    }
    const timer = setInterval(poll, NAV_EVAL_POLL_INTERVAL)
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        controller.abort()
      } else {
        controller = new AbortController()
        poll()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      clearInterval(timer)
      controller.abort()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [enabled, running, benchmarkId, pageOwnsPolling, liveVersion, track])

  const entry = useMemo(() => benchmarkActivity(benchmark), [benchmark])

  // Re-publishing a finished run is harmless: the store drops an entry the
  // user has already acknowledged, so the poll cannot re-light the dot.
  useEffect(() => {
    if (!enabled) return
    publish(ACTIVITY_FEATURES.EVAL, entry)
  }, [enabled, entry, publish])

  const value = useMemo(() => ({ benchmark, track }), [benchmark, track])
  return <EvalActivityContext.Provider value={value}>{children}</EvalActivityContext.Provider>
}

/**
 * Called by the Eval page: publish what the page already polled, and claim
 * ownership of the polling while the page is mounted.
 */
export function useEvalActivityPublisher(benchmark) {
  const context = useContext(EvalActivityContext)
  const track = context?.track
  useLiveActivitySource(ACTIVITY_FEATURES.EVAL, Boolean(context))
  const benchmarkId = benchmark?.benchmark_id
  const status = benchmark?.status
  const signature = JSON.stringify(benchmark?.progress || null)
  useEffect(() => {
    if (!track || !benchmarkId) return
    track(benchmark)
  }, [track, benchmarkId, status, signature])
}
