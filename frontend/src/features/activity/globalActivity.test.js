/**
 * The global activity control: one state for the whole workspace, derived
 * only from work a feature actually published.
 */
import { describe, expect, it } from 'vitest'

import { ACTIVITY_FEATURES, ACTIVITY_STATES } from './activityModel'
import { GLOBAL_ACTIVITY_STATES, summarizeActivity } from './globalActivity'

const running = { state: ACTIVITY_STATES.RUNNING }
const idle = { state: ACTIVITY_STATES.IDLE }

describe('idle', () => {
  it('says Ready when nothing is happening', () => {
    const summary = summarizeActivity({
      [ACTIVITY_FEATURES.CHAT]: idle,
      [ACTIVITY_FEATURES.EVAL]: idle,
    })
    expect(summary.state).toBe(GLOBAL_ACTIVITY_STATES.READY)
    expect(summary.label).toBe('Ready')
    expect(summary.items).toEqual([])
  })

  it('says Ready for an empty store rather than guessing', () => {
    expect(summarizeActivity().label).toBe('Ready')
    expect(summarizeActivity({}).activeCount).toBe(0)
  })
})

describe('active', () => {
  it('counts the work that is running', () => {
    const summary = summarizeActivity({
      [ACTIVITY_FEATURES.CHAT]: running,
      [ACTIVITY_FEATURES.FILES]: { state: ACTIVITY_STATES.QUEUED },
      [ACTIVITY_FEATURES.EVAL]: running,
    })
    expect(summary.state).toBe(GLOBAL_ACTIVITY_STATES.ACTIVE)
    expect(summary.label).toBe('3 active')
    expect(summary.activeCount).toBe(3)
  })

  it('lists the real work behind the count and nothing else', () => {
    const summary = summarizeActivity({
      [ACTIVITY_FEATURES.EVAL]: {
        state: ACTIVITY_STATES.RUNNING,
        progress: { completed: 4, total: 10 },
      },
      [ACTIVITY_FEATURES.CHAT]: idle,
    })
    expect(summary.items).toHaveLength(1)
    expect(summary.items[0]).toMatchObject({
      feature: ACTIVITY_FEATURES.EVAL,
      featureLabel: 'Eval',
      work: 'Evaluation',
      state: 'running',
      stateLabel: 'Running',
      detail: '4/10',
    })
  })

  it('reports progress only when the backend gave both halves of it', () => {
    const summary = summarizeActivity({
      [ACTIVITY_FEATURES.FILES]: { state: ACTIVITY_STATES.RUNNING, progress: { completed: 3 } },
    })
    expect(summary.items[0].detail).toBeNull()
  })

  it('names each feature by its canonical product term', () => {
    const summary = summarizeActivity({ [ACTIVITY_FEATURES.FILES]: running })
    expect(summary.items[0].featureLabel).toBe('Knowledge')
    expect(summary.items[0].work).toBe('Indexing')
  })
})

describe('degraded', () => {
  it('reports a failure ahead of whatever else is running', () => {
    const summary = summarizeActivity({
      [ACTIVITY_FEATURES.CHAT]: running,
      [ACTIVITY_FEATURES.EVAL]: { state: ACTIVITY_STATES.FAILED },
    })
    expect(summary.state).toBe(GLOBAL_ACTIVITY_STATES.DEGRADED)
    expect(summary.label).toBe('Degraded')
    // The running work is still counted and still listed.
    expect(summary.activeCount).toBe(1)
    expect(summary.items.map((item) => item.state)).toEqual(['running', 'failed'])
  })

  it('calls a partial result partial, not completed', () => {
    const summary = summarizeActivity({
      [ACTIVITY_FEATURES.EVAL]: { state: ACTIVITY_STATES.WARNING },
    })
    expect(summary.items[0].stateLabel).toBe('Partial')
    expect(summary.state).toBe(GLOBAL_ACTIVITY_STATES.READY)
  })
})

describe('connectivity', () => {
  it('reports Disconnected rather than a stale count when the browser is offline', () => {
    const summary = summarizeActivity(
      { [ACTIVITY_FEATURES.CHAT]: running },
      { online: false }
    )
    expect(summary.state).toBe(GLOBAL_ACTIVITY_STATES.DISCONNECTED)
    expect(summary.label).toBe('Disconnected')
  })

  it('outranks a failure, because nothing held locally is current', () => {
    const summary = summarizeActivity(
      { [ACTIVITY_FEATURES.EVAL]: { state: ACTIVITY_STATES.FAILED } },
      { online: false }
    )
    expect(summary.label).toBe('Disconnected')
  })
})

describe('never synthesizes', () => {
  it('ignores a feature the activity model does not know', () => {
    const summary = summarizeActivity({ models: running, logs: running })
    expect(summary.items).toEqual([])
    expect(summary.label).toBe('Ready')
  })

  it('ignores an entry whose state is not a real activity state', () => {
    const summary = summarizeActivity({ [ACTIVITY_FEATURES.CHAT]: { state: 'busy-ish' } })
    expect(summary.items).toEqual([])
    expect(summary.label).toBe('Ready')
  })
})
