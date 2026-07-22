/**
 * Tests for logsSlice — log persistence with 1000-entry cap.
 */
import { describe, it, expect } from 'vitest'
import logsReducer, { appendLogs, clearLogs } from './logsSlice'

describe('logsSlice', () => {
  const initialState = { entries: [] }

  it('has correct initial state', () => {
    const state = logsReducer(undefined, { type: '@@INIT' })
    expect(state.entries).toEqual([])
  })

  it('appends logs', () => {
    const state = logsReducer(initialState, appendLogs([
      { log_id: '1', message: 'test log' },
    ]))
    expect(state.entries).toHaveLength(1)
    expect(state.entries[0].message).toBe('test log')
  })

  it('appends multiple logs in batch', () => {
    const logs = Array.from({ length: 5 }, (_, i) => ({ log_id: `${i}`, message: `log ${i}` }))
    const state = logsReducer(initialState, appendLogs(logs))
    expect(state.entries).toHaveLength(5)
  })

  it('caps at 1000 entries', () => {
    const existing = Array.from({ length: 999 }, (_, i) => ({ log_id: `old-${i}` }))
    const state1 = { entries: existing }
    const newLogs = Array.from({ length: 10 }, (_, i) => ({ log_id: `new-${i}` }))

    const state2 = logsReducer(state1, appendLogs(newLogs))
    expect(state2.entries.length).toBeLessThanOrEqual(1000)
    // Newest logs should be at the end
    expect(state2.entries[state2.entries.length - 1].log_id).toBe('new-9')
  })

  it('clearLogs resets entries', () => {
    const state = logsReducer(
      { entries: [{ log_id: '1' }] },
      clearLogs()
    )
    expect(state.entries).toEqual([])
  })
})
