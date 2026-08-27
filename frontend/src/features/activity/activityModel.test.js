/**
 * The mapping layer, tested without a DOM.
 *
 * Every feature's status vocabulary funnels through here, so these cases are
 * the contract the navigation renders against.
 */
import { describe, expect, it } from 'vitest'
import {
  ACTIVITY_STATES,
  acknowledgeActivity,
  describeActivity,
  isActiveState,
  isTerminalState,
  mapBenchmarkStatus,
  mapChatState,
  normalizeActivity,
} from './activityModel'

describe('benchmark status mapping', () => {
  it('maps an absent benchmark to idle', () => {
    expect(mapBenchmarkStatus(undefined)).toBe(ACTIVITY_STATES.IDLE)
  })

  it('maps queued to queued', () => {
    expect(mapBenchmarkStatus('queued')).toBe(ACTIVITY_STATES.QUEUED)
  })

  it('maps running to running', () => {
    expect(mapBenchmarkStatus('running')).toBe(ACTIVITY_STATES.RUNNING)
  })

  it('maps completed to success', () => {
    expect(mapBenchmarkStatus('completed')).toBe(ACTIVITY_STATES.SUCCESS)
  })

  it('maps partial and interrupted to warning, never to success', () => {
    expect(mapBenchmarkStatus('partial')).toBe(ACTIVITY_STATES.WARNING)
    expect(mapBenchmarkStatus('interrupted')).toBe(ACTIVITY_STATES.WARNING)
  })

  it('maps failed to failed', () => {
    expect(mapBenchmarkStatus('failed')).toBe(ACTIVITY_STATES.FAILED)
  })
})

describe('chat state mapping', () => {
  it('maps the streaming lifecycle', () => {
    expect(mapChatState('idle')).toBe(ACTIVITY_STATES.IDLE)
    expect(mapChatState('connecting')).toBe(ACTIVITY_STATES.RUNNING)
    expect(mapChatState('streaming')).toBe(ACTIVITY_STATES.RUNNING)
    expect(mapChatState('done')).toBe(ACTIVITY_STATES.SUCCESS)
    expect(mapChatState('error')).toBe(ACTIVITY_STATES.FAILED)
  })
})

describe('acknowledgement', () => {
  it('clears terminal state', () => {
    for (const state of [ACTIVITY_STATES.SUCCESS, ACTIVITY_STATES.WARNING, ACTIVITY_STATES.FAILED]) {
      expect(acknowledgeActivity({ state }).state).toBe(ACTIVITY_STATES.IDLE)
    }
  })

  it('leaves work that is still running alone', () => {
    for (const state of [ACTIVITY_STATES.QUEUED, ACTIVITY_STATES.RUNNING]) {
      expect(acknowledgeActivity({ state, label: 'Regular E2E' })).toMatchObject({ state })
    }
  })
})

describe('bounded metadata', () => {
  it('drops unknown keys and unknown states', () => {
    const entry = normalizeActivity({ state: 'exploded', prompt: 'secret question' })
    expect(entry).toEqual({ state: ACTIVITY_STATES.IDLE })
    const running = normalizeActivity({
      state: ACTIVITY_STATES.RUNNING,
      label: 'Regular E2E',
      prompt: 'secret question',
    })
    expect(running.prompt).toBeUndefined()
  })

  it('truncates long text rather than carrying it into the nav', () => {
    const entry = normalizeActivity({ state: ACTIVITY_STATES.FAILED, message: 'x'.repeat(400) })
    expect(entry.message.length).toBeLessThanOrEqual(72)
  })

  it('keeps progress only when both halves are real', () => {
    expect(normalizeActivity({ state: 'running', progress: { completed: 18, total: 30 } }).progress)
      .toEqual({ completed: 18, total: 30 })
    expect(normalizeActivity({ state: 'running', progress: { completed: 18 } }).progress)
      .toBeUndefined()
  })
})

describe('status text', () => {
  it('describes a running benchmark with its progress and profile', () => {
    const text = describeActivity('eval', {
      state: ACTIVITY_STATES.RUNNING,
      progress: { completed: 18, total: 30 },
      label: 'Regular E2E',
    })
    expect(text).toBe('Eval — benchmark running · 18/30 · Regular E2E')
  })

  it('falls back to the feature name when nothing is happening', () => {
    expect(describeActivity('chat', { state: ACTIVITY_STATES.IDLE })).toBe('Chat')
  })
})

describe('state predicates', () => {
  it('separates active from terminal', () => {
    expect(isActiveState(ACTIVITY_STATES.RUNNING)).toBe(true)
    expect(isActiveState(ACTIVITY_STATES.SUCCESS)).toBe(false)
    expect(isTerminalState(ACTIVITY_STATES.WARNING)).toBe(true)
    expect(isTerminalState(ACTIVITY_STATES.IDLE)).toBe(false)
  })
})
