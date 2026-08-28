/**
 * Auto-refresh lifecycle tests for `useLogs` (REACT-19-01).
 *
 * The 2s poll belongs to `autoRefresh` alone. It used to be keyed on the
 * fetcher as well, so editing the line count or toggling a service tore the
 * interval down and started a new one mid-stream. Routing the tick through an
 * Effect Event keeps the timer stable while still calling the newest fetcher.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getLogs } = vi.hoisted(() => ({ getLogs: vi.fn() }))

vi.mock('@/features/logs/services/logService', () => ({
  default: { getLogs, getAllLogs: vi.fn() },
}))

import { useLogs } from './useLogs'

// Stable reference, as the Redux-backed caller supplies.
const SERVICES = ['gateway']

describe('useLogs auto-refresh', () => {
  beforeEach(() => {
    getLogs.mockResolvedValue({ service: 'gateway', logs: ['hello'], source: 'docker' })
  })

  it('keeps one poll timer when the line count changes, and polls with the new value', async () => {
    // Fake timers replace the globals, so spy *after* installing them.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const setInterval = vi.spyOn(globalThis, 'setInterval')
    const clearInterval = vi.spyOn(globalThis, 'clearInterval')

    try {
      const { rerender } = renderHook(({ lines }) => useLogs(SERVICES, lines, true), {
        initialProps: { lines: 100 },
      })
      await waitFor(() => expect(getLogs).toHaveBeenCalledWith('gateway', 100))

      const pollTimers = () =>
        setInterval.mock.calls
          .map((args, index) => [args, setInterval.mock.results[index]])
          .filter(([args]) => args[1] === 2000)
          .map(([, result]) => result.value)

      expect(pollTimers()).toHaveLength(1)
      const [timerId] = pollTimers()

      rerender({ lines: 250 })
      await waitFor(() => expect(getLogs).toHaveBeenCalledWith('gateway', 250))

      // The line change refetched immediately but did not restart the poll.
      expect(pollTimers()).toHaveLength(1)

      getLogs.mockClear()
      await act(async () => { await vi.advanceTimersByTimeAsync(2000) })

      // The stable timer still reached the latest fetcher.
      expect(getLogs).toHaveBeenCalledWith('gateway', 250)
      expect(pollTimers()).toHaveLength(1)
      expect(pollTimers()[0]).toBe(timerId)
      // Scoped to the poll timer: unrelated machinery clears timers of its own.
      expect(clearInterval.mock.calls.map(([id]) => id)).not.toContain(timerId)
    } finally {
      vi.useRealTimers()
      setInterval.mockRestore()
      clearInterval.mockRestore()
    }
  })

  it('stops polling when auto-refresh is turned off', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const { rerender } = renderHook(({ auto }) => useLogs(SERVICES, 100, auto), {
        initialProps: { auto: true },
      })
      await waitFor(() => expect(getLogs).toHaveBeenCalled())

      rerender({ auto: false })
      getLogs.mockClear()

      await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
      expect(getLogs).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })
})
