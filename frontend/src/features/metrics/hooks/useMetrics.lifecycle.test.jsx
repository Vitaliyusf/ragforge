/**
 * Subscription-lifecycle tests for `useMetrics` (REACT-19-01).
 *
 * The 30s poll and the `visibilitychange` listener are a mount-scoped
 * lifecycle; only the fetch is reactive to section/window/tenant. They used to
 * live in one Effect keyed on the fetcher, so every window change detached and
 * reattached the document listener and reset the poll phase.
 *
 * These pin the split, and pin that the timer still runs the *newest* fetcher —
 * the whole point of routing it through an Effect Event.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { getOverview } = vi.hoisted(() => ({ getOverview: vi.fn() }))

vi.mock('../services/metricsService', () => ({
  default: {
    getOverview,
    getLatency: vi.fn(),
    getRetrieval: vi.fn(),
    getQuality: vi.fn(),
    getPipeline: vi.fn(),
  },
}))

import { useMetrics } from './useMetrics'

const visibilityCalls = (spy) => spy.mock.calls.filter(([event]) => event === 'visibilitychange')

describe('useMetrics subscription lifecycle', () => {
  let addSpy
  let removeSpy

  beforeEach(() => {
    getOverview.mockResolvedValue({ data: { turns: 1 }, prometheus_available: true })
    addSpy = vi.spyOn(document, 'addEventListener')
    removeSpy = vi.spyOn(document, 'removeEventListener')
  })

  afterEach(() => {
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it('registers the visibility listener once and keeps it across window changes', async () => {
    const { rerender } = renderHook(({ range }) => useMetrics('overview', { window: range }), {
      initialProps: { range: '1h' },
    })

    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1))
    expect(visibilityCalls(addSpy)).toHaveLength(1)

    rerender({ range: '24h' })

    // The window change still reloads...
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(2))
    expect(getOverview).toHaveBeenLastCalledWith(expect.objectContaining({ window: '24h' }))
    // ...but does not churn the subscription.
    expect(visibilityCalls(addSpy)).toHaveLength(1)
    expect(visibilityCalls(removeSpy)).toHaveLength(0)
  })

  it('unsubscribes exactly once on unmount', async () => {
    const { unmount } = renderHook(() => useMetrics('overview', { window: '1h' }))
    await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1))

    await act(async () => { unmount() })

    expect(visibilityCalls(removeSpy)).toHaveLength(1)
    expect(visibilityCalls(removeSpy)[0][1]).toBe(visibilityCalls(addSpy)[0][1])
  })

  it('polls with the latest window without having resubscribed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const { rerender } = renderHook(({ range }) => useMetrics('overview', { window: range }), {
        initialProps: { range: '1h' },
      })
      await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(1))

      rerender({ range: '24h' })
      await waitFor(() => expect(getOverview).toHaveBeenCalledTimes(2))

      await act(async () => { await vi.advanceTimersByTimeAsync(30000) })

      expect(getOverview).toHaveBeenCalledTimes(3)
      expect(getOverview).toHaveBeenLastCalledWith(expect.objectContaining({ window: '24h' }))
      expect(visibilityCalls(addSpy)).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })
})
