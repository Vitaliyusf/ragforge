/**
 * Tests for the three benchmark timing concepts.
 *
 * These exist because the history row used to mix two clocks: it labelled
 * `created_at` as "Started" and then measured its duration from
 * `started_at`, so the two numbers on one row could not be reconciled with
 * each other. Each span here is pinned to the pair of timestamps its label
 * names, and a run missing one of them is pinned to a dash.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  EMPTY,
  benchmarkExecutionDuration,
  benchmarkQueueDuration,
  benchmarkTotalDuration,
  durationBetween,
} from './evalProfiles'
import { benchmarkTiming } from './runReport'

const CREATED = '2026-09-01T19:11:22.000Z'
const STARTED = '2026-09-01T19:14:39.000Z' // 3m 17s after creation
const FINISHED = '2026-09-01T19:20:09.000Z' // 5m 30s after start

/** Freeze the clock so an unfinished span has a duration to assert on. */
function atNow(iso) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(iso))
}

afterEach(() => {
  vi.useRealTimers()
})

describe('benchmark timing spans', () => {
  it('measures queue/preflight from creation to the actual start', () => {
    expect(benchmarkQueueDuration(CREATED, STARTED)).toBe('3m 17s')
  })

  it('measures execution from the actual start to the finish', () => {
    expect(benchmarkExecutionDuration(STARTED, FINISHED)).toBe('5m 30s')
  })

  it('measures total elapsed from creation to the finish', () => {
    expect(benchmarkTotalDuration(CREATED, FINISHED)).toBe('8m 47s')
  })

  it('never measures execution from creation', () => {
    expect(benchmarkExecutionDuration(STARTED, FINISHED)).not.toBe(
      benchmarkTotalDuration(CREATED, FINISHED)
    )
  })

  it('grows a queued run against the clock from its creation time', () => {
    atNow('2026-09-01T19:13:00.000Z')
    expect(benchmarkQueueDuration(CREATED, null)).toBe('1m 38s')
    expect(benchmarkTotalDuration(CREATED, null)).toBe('1m 38s')
    // Nothing has executed yet, and no elapsed time may be attributed to it.
    expect(benchmarkExecutionDuration(null, null)).toBe(EMPTY)
  })

  it('grows a running run from its start while its total grows from creation', () => {
    atNow('2026-09-01T19:16:39.000Z')
    expect(benchmarkQueueDuration(CREATED, STARTED)).toBe('3m 17s')
    expect(benchmarkExecutionDuration(STARTED, null)).toBe('2m 00s')
    expect(benchmarkTotalDuration(CREATED, null)).toBe('5m 17s')
  })

  it('reports a dash for a legacy run whose timestamps were never written', () => {
    expect(benchmarkQueueDuration(null, null)).toBe(EMPTY)
    expect(benchmarkExecutionDuration(undefined, FINISHED)).toBe(EMPTY)
    expect(benchmarkTotalDuration('', FINISHED)).toBe(EMPTY)
    expect(benchmarkExecutionDuration('not-a-timestamp', FINISHED)).toBe(EMPTY)
  })

  it('shows contradictory timestamps as a signed span rather than as zero', () => {
    // Clamping this to `0m 00s` would dress a broken record up as a run
    // that finished the instant it started, which is believable and wrong.
    const backwards = durationBetween(FINISHED, STARTED)
    expect(backwards).toBe('-5m 30s')
    expect(backwards).not.toBe('0m 00s')
    expect(benchmarkTotalDuration(FINISHED, CREATED)).toBe('-8m 47s')
  })
})

describe('benchmarkTiming', () => {
  const run = {
    benchmark_id: 'bm-1',
    created_at: CREATED,
    started_at: STARTED,
    finished_at: FINISHED,
  }

  it('breaks a finished run into queue, execution and total', () => {
    const timing = benchmarkTiming(run)
    expect(timing.spans.map((span) => [span.key, span.value])).toEqual([
      ['queue', '3m 17s'],
      ['execution', '5m 30s'],
      ['total', '8m 47s'],
    ])
  })

  it('keeps the three points of the run apart from each other', () => {
    const timing = benchmarkTiming(run)
    expect(timing.createdAt).toBe(CREATED)
    expect(timing.startedAt).toBe(STARTED)
    expect(timing.finishedAt).toBe(FINISHED)
  })

  it('dashes every span a legacy run has no timestamps for', () => {
    const timing = benchmarkTiming({ benchmark_id: 'bm-legacy' })
    expect(timing.spans.every((span) => span.value === EMPTY)).toBe(true)
    expect(timing.startedLabel).toBe(EMPTY)
  })
})
