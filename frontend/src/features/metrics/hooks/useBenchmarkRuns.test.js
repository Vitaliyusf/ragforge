import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../services/metricsService', () => ({ default: { listBenchmarkRuns: vi.fn(), getBenchmarkRun: vi.fn(), startBenchmarkRun: vi.fn(), downloadBenchmark: vi.fn() } }))

import metricsService from '../services/metricsService'
import { useBenchmarkRuns } from './useBenchmarkRuns'

function setVisibility(state) {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('useBenchmarkRuns polling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setVisibility('visible')
  })
  afterEach(() => {
    vi.useRealTimers()
    setVisibility('visible')
  })

  it('restores an active run, preferring it over a newer terminal run', async () => {
    metricsService.listBenchmarkRuns.mockResolvedValue({ benchmarks: [
      { benchmark_id: 'terminal', status: 'completed' }, { benchmark_id: 'active', status: 'running' },
    ] })
    const { result } = renderHook(() => useBenchmarkRuns('dataset-1'))
    await act(async () => {})
    expect(metricsService.listBenchmarkRuns).toHaveBeenCalledWith(expect.objectContaining({ datasetId: 'dataset-1' }))
    expect(result.current.benchmark).toEqual(expect.objectContaining({ benchmark_id: 'active' }))
  })

  it('restores the latest terminal run when there is no active run', async () => {
    metricsService.listBenchmarkRuns.mockResolvedValue({ benchmarks: [{ benchmark_id: 'latest', status: 'completed' }] })
    const { result } = renderHook(() => useBenchmarkRuns('dataset-1'))
    await act(async () => {})
    expect(result.current.benchmark).toEqual(expect.objectContaining({ benchmark_id: 'latest' }))
  })

  it('keeps the last known run when a polling update fails', async () => {
    metricsService.listBenchmarkRuns.mockResolvedValue({ benchmarks: [] })
    metricsService.startBenchmarkRun.mockResolvedValue({ benchmark: { benchmark_id: 'b-1', status: 'running' } })
    metricsService.getBenchmarkRun.mockRejectedValue(new Error('Network unavailable'))
    const { result } = renderHook(() => useBenchmarkRuns('dataset-1'))
    await act(async () => { await result.current.start() })
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(result.current.benchmark).toEqual(expect.objectContaining({ benchmark_id: 'b-1', status: 'running' }))
    expect(result.current.error).toBe('Network unavailable')
  })

  it('resumes polling after the tab is hidden and shown again', async () => {
    let call = 0
    metricsService.getBenchmarkRun.mockImplementation(async (_id, { signal } = {}) => {
      // Mirrors real fetch: a request made with an already-aborted signal
      // rejects immediately instead of ever reaching the network.
      if (signal?.aborted) {
        const err = new Error('The operation was aborted')
        err.name = 'AbortError'
        throw err
      }
      call += 1
      return { benchmark: { benchmark_id: 'b-1', status: call < 3 ? 'running' : 'completed', phases: [] } }
    })
    metricsService.startBenchmarkRun.mockResolvedValue({
      benchmark: { benchmark_id: 'b-1', status: 'running', phases: [] },
    })

    const { result } = renderHook(() => useBenchmarkRuns('dataset-1'))
    await act(async () => {
      await result.current.start()
    })
    expect(result.current.benchmark).toEqual(expect.objectContaining({ benchmark_id: 'b-1' }))

    // Backgrounding the tab mid-poll aborts the in-flight request.
    setVisibility('hidden')
    // Returning to the tab must not leave every future poll poisoned by
    // the controller aborted above.
    setVisibility('visible')

    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })

    expect(result.current.benchmark?.status).toBe('completed')
  })
})
