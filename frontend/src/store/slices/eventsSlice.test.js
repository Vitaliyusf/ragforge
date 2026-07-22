/**
 * Tests for eventsSlice — cross-feature event bus.
 */
import { describe, it, expect } from 'vitest'
import eventsReducer, { filesChanged, chatDeleted } from './eventsSlice'

describe('eventsSlice', () => {
  const initialState = { filesVersion: 0, chatDeletedVersion: 0 }

  it('has correct initial state', () => {
    const state = eventsReducer(undefined, { type: '@@INIT' })
    expect(state).toEqual(initialState)
  })

  it('increments filesVersion on filesChanged', () => {
    let state = eventsReducer(initialState, filesChanged())
    expect(state.filesVersion).toBe(1)

    state = eventsReducer(state, filesChanged())
    expect(state.filesVersion).toBe(2)
  })

  it('increments chatDeletedVersion on chatDeleted', () => {
    let state = eventsReducer(initialState, chatDeleted())
    expect(state.chatDeletedVersion).toBe(1)
  })

  it('filesChanged does not affect chatDeletedVersion', () => {
    const state = eventsReducer(initialState, filesChanged())
    expect(state.chatDeletedVersion).toBe(0)
  })

  it('chatDeleted does not affect filesVersion', () => {
    const state = eventsReducer(initialState, chatDeleted())
    expect(state.filesVersion).toBe(0)
  })
})
