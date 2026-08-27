/**
 * Eval activity: one poller, and a state that survives leaving the page.
 *
 * The interesting cases are the two boundaries — the Eval page mounting
 * (which must take polling over, not add to it) and unmounting (after which
 * the nav has to keep tracking the run on its own).
 */
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/features/metrics/services/metricsService', () => ({
  default: { listBenchmarkRuns: vi.fn(), getBenchmarkRun: vi.fn() },
}))

import metricsService from '@/features/metrics/services/metricsService'
import { ACTIVITY_FEATURES, ACTIVITY_STATES } from './activityModel'
import { ActivityProvider, useActivity, useFeatureActivity } from './ActivityContext'
import {
  EvalActivityProvider,
  NAV_EVAL_POLL_INTERVAL,
  useEvalActivityPublisher,
} from './sources/EvalActivityProvider'

const RUNNING = {
  benchmark_id: 'b-1',
  status: 'running',
  profile: 'full_quality',
  progress: { items_per_phase: 30, completed_phases: 0, executable_phases: 2 },
  phases: [{ name: 'end_to_end_regular', status: 'running', item_progress: { items_completed: 18 } }],
}

/** Stands in for the nav: renders the Eval entry as text. */
function ActivityProbe() {
  const activity = useFeatureActivity(ACTIVITY_FEATURES.EVAL)
  return (
    <div>
      <span data-testid="state">{activity.state}</span>
      <span data-testid="progress">
        {activity.progress ? `${activity.progress.completed}/${activity.progress.total}` : ''}
      </span>
      <span data-testid="label">{activity.label || ''}</span>
    </div>
  )
}

/** Stands in for the Eval page and its own 3s poll. */
function FakeEvalPage({ benchmark }) {
  useEvalActivityPublisher(benchmark)
  return null
}

function AcknowledgeButton() {
  const { acknowledge } = useActivity()
  return (
    <button type="button" onClick={() => acknowledge(ACTIVITY_FEATURES.EVAL)}>
      open eval
    </button>
  )
}

function renderShell(ui) {
  return render(
    <ActivityProvider>
      <EvalActivityProvider>
        <ActivityProbe />
        <AcknowledgeButton />
        {ui}
      </EvalActivityProvider>
    </ActivityProvider>
  )
}

beforeEach(() => {
  vi.useFakeTimers()
  metricsService.listBenchmarkRuns.mockResolvedValue({ benchmarks: [] })
  metricsService.getBenchmarkRun.mockResolvedValue({ benchmark: RUNNING })
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('eval activity', () => {
  it('makes the nav running while a benchmark executes, with the server progress', async () => {
    renderShell(<FakeEvalPage benchmark={RUNNING} />)
    await act(async () => {})
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.RUNNING)
    expect(screen.getByTestId('progress')).toHaveTextContent('18/30')
    expect(screen.getByTestId('label')).toHaveTextContent('Regular E2E')
  })

  it('does not add a second poll loop while the Eval page owns polling', async () => {
    renderShell(<FakeEvalPage benchmark={RUNNING} />)
    await act(async () => {})
    metricsService.getBenchmarkRun.mockClear()
    await act(async () => { vi.advanceTimersByTime(NAV_EVAL_POLL_INTERVAL * 4) })
    expect(metricsService.getBenchmarkRun).not.toHaveBeenCalled()
  })

  it('keeps the running state and takes polling over once the page unmounts', async () => {
    const view = renderShell(<FakeEvalPage benchmark={RUNNING} />)
    await act(async () => {})
    view.rerender(
      <ActivityProvider>
        <EvalActivityProvider>
          <ActivityProbe />
          <AcknowledgeButton />
        </EvalActivityProvider>
      </ActivityProvider>
    )
    await act(async () => {})
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.RUNNING)
    metricsService.getBenchmarkRun.mockClear()
    await act(async () => { vi.advanceTimersByTime(NAV_EVAL_POLL_INTERVAL) })
    expect(metricsService.getBenchmarkRun).toHaveBeenCalledWith('b-1', expect.anything())
  })

  it('transitions to success when the background poll sees the run complete', async () => {
    const view = renderShell(<FakeEvalPage benchmark={RUNNING} />)
    await act(async () => {})
    view.rerender(
      <ActivityProvider>
        <EvalActivityProvider>
          <ActivityProbe />
          <AcknowledgeButton />
        </EvalActivityProvider>
      </ActivityProvider>
    )
    metricsService.getBenchmarkRun.mockResolvedValue({
      benchmark: { ...RUNNING, status: 'completed' },
    })
    await act(async () => { vi.advanceTimersByTime(NAV_EVAL_POLL_INTERVAL) })
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.SUCCESS)
  })

  it('transitions to failed', async () => {
    renderShell(<FakeEvalPage benchmark={{ ...RUNNING, status: 'failed' }} />)
    await act(async () => {})
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.FAILED)
  })

  it('restores a run that is still executing after a reload, and only an active one', async () => {
    metricsService.listBenchmarkRuns.mockResolvedValue({
      benchmarks: [{ benchmark_id: 'old', status: 'completed' }, RUNNING],
    })
    renderShell(null)
    await act(async () => {})
    expect(metricsService.listBenchmarkRuns).toHaveBeenCalledWith(
      expect.objectContaining({ limit: expect.any(Number) })
    )
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.RUNNING)
  })

  it('stays idle — and silent — when no run is active', async () => {
    renderShell(null)
    await act(async () => {})
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.IDLE)
    await act(async () => { vi.advanceTimersByTime(NAV_EVAL_POLL_INTERVAL * 5) })
    expect(metricsService.getBenchmarkRun).not.toHaveBeenCalled()
  })

  it('does not light the marker again once the terminal run has been opened', async () => {
    const { getByText } = renderShell(<FakeEvalPage benchmark={{ ...RUNNING, status: 'completed' }} />)
    await act(async () => {})
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.SUCCESS)
    await act(async () => { getByText('open eval').click() })
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.IDLE)
    await act(async () => { vi.advanceTimersByTime(NAV_EVAL_POLL_INTERVAL * 3) })
    expect(screen.getByTestId('state')).toHaveTextContent(ACTIVITY_STATES.IDLE)
  })
})
