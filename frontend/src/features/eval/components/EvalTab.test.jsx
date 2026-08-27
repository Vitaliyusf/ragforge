/**
 * Tests for the Eval workspace shell.
 *
 * Both hooks are mocked: these cover what the page renders and which
 * handler each control reaches, not polling. The recurring assertions are
 * the two the redesign must not have broken — an unmeasured figure is still
 * a dash, and a destructive action still asks first.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockUseEvalRuns, mockUseBenchmarkRuns } = vi.hoisted(() => ({
  mockUseEvalRuns: vi.fn(),
  mockUseBenchmarkRuns: vi.fn(),
}))

vi.mock('@/features/metrics/hooks/useEvalRuns', () => ({
  useEvalRuns: mockUseEvalRuns,
  isRunning: (run) => Boolean(run?.run_id) && !['completed', 'failed'].includes(run?.status),
}))
vi.mock('@/features/metrics/hooks/useBenchmarkRuns', () => ({
  useBenchmarkRuns: mockUseBenchmarkRuns,
}))

import EvalTab from './EvalTab'

const DATASET = {
  dataset_id: 'd-1',
  name: 'golden_smoke_30',
  item_count: 30,
  dataset_version: 2,
  dataset_sha256: '20b2ea7875df9e04c54d0b8af98f5ea6a96b764b0169a7763d01aa51b2887b3e',
  last_run_at: '2026-08-26T10:00:00Z',
}

function evalState(overrides = {}) {
  return {
    datasets: [DATASET],
    datasetId: 'd-1',
    selectDataset: vi.fn(),
    runs: [],
    run: null,
    running: false,
    loading: false,
    error: null,
    busy: false,
    startRun: vi.fn(),
    estimateRunCost: vi.fn(),
    importDataset: vi.fn(),
    deleteDataset: vi.fn(),
    refresh: vi.fn(),
    ...overrides,
  }
}

function benchmarkState(overrides = {}) {
  return {
    benchmark: null,
    history: [],
    error: null,
    busy: false,
    start: vi.fn(),
    select: vi.fn(),
    download: vi.fn(),
    ...overrides,
  }
}

function setup({ evalOverrides = {}, benchmarkOverrides = {} } = {}) {
  const evalHook = evalState(evalOverrides)
  const benchmarkHook = benchmarkState(benchmarkOverrides)
  mockUseEvalRuns.mockReturnValue(evalHook)
  mockUseBenchmarkRuns.mockReturnValue(benchmarkHook)
  render(<EvalTab />)
  return { evalHook, benchmarkHook }
}

describe('EvalTab page chrome', () => {
  beforeEach(() => {
    mockUseEvalRuns.mockReset()
    mockUseBenchmarkRuns.mockReset()
  })

  it('titles itself Eval rather than Metrics', () => {
    setup()
    expect(screen.getByRole('heading', { name: 'Eval' })).toBeInTheDocument()
    expect(
      screen.getByText('Golden sets, benchmark profiles and quality diagnostics')
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Metrics' })).not.toBeInTheDocument()
  })

  it('does not carry the metrics time-window or tenant controls', () => {
    setup()
    // A run is a document with its own lifecycle: a 24-hour window means
    // nothing to it, and offering one would imply it filtered something.
    expect(screen.queryByLabelText('Time window')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Tenant')).not.toBeInTheDocument()
    expect(screen.queryByText(/Last 24 hours/i)).not.toBeInTheDocument()
  })

  it('gives every control an accessible name', () => {
    setup()
    for (const button of screen.getAllByRole('button')) {
      const name = button.getAttribute('aria-label') || button.textContent.trim()
      expect(name, 'found a button with no accessible name').not.toBe('')
    }
  })

  it('keeps wide content inside its own scroller rather than the page', async () => {
    // jsdom does not lay anything out, so this is the structural half of the
    // guarantee: every table that can outgrow the viewport sits in its own
    // horizontal scroller, and no surface pins a width the page must widen
    // to fit. The visual half is a manual check at 1440px, 1024px and mobile.
    const user = userEvent.setup()
    const { evalHook } = setup({
      evalOverrides: {
        run: {
          run_id: 'r-1',
          status: 'completed',
          dataset_sha256: DATASET.dataset_sha256,
          dataset_version: 2,
          match_mode: 'chunk_id',
          results: { mrr: 0.7, recall_at_k: { 5: 1 }, items_evaluated: 30 },
          per_item: [{ item_id: 'i-1', query: 'q', reciprocal_rank: 1, first_hit_rank: 1 }],
        },
      },
    })
    expect(evalHook.run).toBeTruthy()

    await user.click(screen.getByText('Scores at k'))
    await user.click(screen.getByText('Per-item results'))

    for (const table of screen.getAllByRole('table')) {
      expect(table.closest('.overflow-x-auto'), 'a table with no scroller of its own').not.toBeNull()
    }
    for (const node of document.querySelectorAll('[class*="min-w-["]')) {
      expect(node.className).not.toMatch(/min-w-\[\d{3,}px\]/)
    }
  })

  it('explains how to build a golden set when there is none', () => {
    setup({ evalOverrides: { datasets: [], datasetId: '' } })
    expect(screen.getByText('No golden set yet')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start benchmark/i })).not.toBeInTheDocument()
  })
})

describe('EvalTab evaluation setup', () => {
  beforeEach(() => {
    mockUseEvalRuns.mockReset()
    mockUseBenchmarkRuns.mockReset()
  })

  it('shows the dataset and its metadata without a row each', () => {
    setup()
    expect(screen.getByLabelText('Golden set')).toHaveTextContent('golden_smoke_30')
    expect(screen.getByText('Items')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(screen.getByText('v2')).toBeInTheDocument()
    expect(screen.getByText('20b2ea7875df')).toBeInTheDocument()
  })

  it('selects another dataset through the themed select', async () => {
    const user = userEvent.setup()
    const second = { ...DATASET, dataset_id: 'd-2', name: 'golden_regression_80' }
    const { evalHook } = setup({ evalOverrides: { datasets: [DATASET, second] } })

    await user.click(screen.getByLabelText('Golden set'))
    await user.click(await screen.findByRole('option', { name: 'golden_regression_80' }))

    expect(evalHook.selectDataset).toHaveBeenCalledWith('d-2')
  })

  it('opens the importer from the setup card', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: /^Import$/i }))
    expect(screen.getByRole('dialog')).toHaveTextContent(/golden set/i)
  })

  it('keeps delete out of the primary row and behind a confirmation', async () => {
    const user = userEvent.setup()
    const { evalHook } = setup()

    // Not a button sitting beside the metrics: it lives in the overflow menu.
    expect(screen.queryByRole('button', { name: /^Delete/i })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Dataset actions' }))
    await user.click(screen.getByRole('menuitem', { name: /delete golden set/i }))

    expect(evalHook.deleteDataset).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(/Delete this golden set\?/i)

    await user.click(within(dialog).getByRole('button', { name: 'Delete golden set' }))
    expect(evalHook.deleteDataset).toHaveBeenCalledWith('d-1')
  })
})

describe('EvalTab run surface', () => {
  beforeEach(() => {
    mockUseEvalRuns.mockReset()
    mockUseBenchmarkRuns.mockReset()
  })

  it('offers exactly one primary benchmark action', () => {
    setup()
    const start = screen.getByRole('button', { name: /start benchmark/i })
    expect(start).toBeInTheDocument()

    // The ad-hoc run is still here, and still secondary: collapsed by
    // default and never drawn as a second primary button.
    const single = screen.getByRole('button', { name: /run evaluation/i })
    const disclosure = single.closest('details')
    expect(disclosure).not.toBeNull()
    expect(disclosure.open).toBe(false)
    expect(within(disclosure).getByText('Single evaluation')).toBeInTheDocument()

    const primaryish = screen
      .getAllByRole('button')
      .filter((button) => button.className.includes('bg-[var(--primary)]'))
    expect(primaryish).toEqual([start])
  })

  it('keeps the single evaluation reachable behind its disclosure', async () => {
    const user = userEvent.setup()
    const { evalHook } = setup()

    await user.click(screen.getByText('Single evaluation'))
    expect(screen.getByLabelText('Run mode')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /run evaluation/i }))
    expect(evalHook.startRun).toHaveBeenCalledWith('retrieval')
  })
})

describe('EvalTab active benchmark', () => {
  const RUNNING = {
    benchmark_id: 'b-1',
    status: 'running',
    profile: 'full_quality',
    started_at: '2026-08-26T12:00:00Z',
    progress: { completed_phases: 1, executable_phases: 2, items_per_phase: 30 },
    phases: [
      { name: 'retrieval_base', status: 'completed', results: { mrr: 0.8, mean_latency_ms: 11 } },
      {
        name: 'end_to_end_regular',
        status: 'running',
        item_progress: {
          items_completed: 18,
          items_succeeded: 17,
          items_guardrail_blocked: 1,
          items_failed: 0,
          items_in_flight: 4,
        },
      },
      { name: 'retrieval_extended', status: 'unsupported' },
    ],
  }

  beforeEach(() => {
    mockUseEvalRuns.mockReset()
    mockUseBenchmarkRuns.mockReset()
  })

  it('makes the running phase, its progress and its outcomes the focal point', () => {
    setup({ benchmarkOverrides: { benchmark: RUNNING } })

    expect(screen.getByRole('heading', { name: 'Active run' })).toBeInTheDocument()
    expect(screen.getAllByText('Running').length).toBeGreaterThan(0)
    expect(screen.getByText(/18 \/ 30 items · 60%/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '60')
    expect(screen.getByText('Guardrail blocked')).toBeInTheDocument()
    expect(screen.getByText('In flight')).toBeInTheDocument()
    expect(screen.getByText(/safe to leave this page/i)).toBeInTheDocument()
  })

  it('reads an unsupported phase as unsupported, never as a failure', () => {
    setup({ benchmarkOverrides: { benchmark: RUNNING } })
    const stepper = screen.getByRole('list', { name: 'Benchmark phases' })
    expect(within(stepper).getByText('Not supported')).toBeInTheDocument()
    expect(within(stepper).queryByText('Failed')).not.toBeInTheDocument()
    expect(within(stepper).getByText('Completed')).toBeInTheDocument()
  })

  it('blocks a second benchmark while one is running', () => {
    setup({ benchmarkOverrides: { benchmark: RUNNING } })
    expect(screen.getByRole('button', { name: /benchmark running/i })).toBeDisabled()
  })

  it('offers no export while the run is still going', () => {
    setup({ benchmarkOverrides: { benchmark: RUNNING } })
    expect(
      screen.queryByRole('button', { name: /download diagnostic zip/i })
    ).not.toBeInTheDocument()
  })

  it.each([
    ['completed', /every executable phase finished/i],
    ['partial', /some phases did not finish/i],
    ['interrupted', /stopped before finishing/i],
    ['failed', /stopped after an error/i],
  ])('states in words what a %s run means, not only in colour', (status, note) => {
    setup({
      benchmarkOverrides: {
        benchmark: { ...RUNNING, status, phases: [], error: status === 'failed' ? 'Vector store unavailable' : null },
      },
    })
    expect(screen.getByRole('heading', { name: 'Latest run' })).toBeInTheDocument()
    expect(screen.getByText(note)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /download diagnostic zip/i })
    ).toBeInTheDocument()
  })

  it('surfaces the error of a failed run on the page', () => {
    setup({
      benchmarkOverrides: {
        benchmark: { ...RUNNING, status: 'failed', phases: [], error: 'Vector store unavailable' },
      },
    })
    expect(screen.getByText('Vector store unavailable')).toBeInTheDocument()
  })

  it('exports the displayed run by its own id', async () => {
    const user = userEvent.setup()
    const { benchmarkHook } = setup({
      benchmarkOverrides: { benchmark: { ...RUNNING, status: 'completed', phases: [] } },
    })
    await user.click(screen.getByRole('button', { name: /download diagnostic zip/i }))
    // Not the click event: download() treats its argument as a benchmark id.
    expect(benchmarkHook.download).toHaveBeenCalledWith()
  })
  /**
   * jsdom cannot lay flexbox out, so these pin the rules rather than the
   * pixels.
   */
  it('scrolls the full width, and caps the width one level in', () => {
    setup()
    const viewport = document.body.querySelector('.overflow-y-auto')
    expect(viewport).not.toBeNull()
    // The scroll viewport must not be the width-capped column: a scrollbar
    // on a `max-w-*` element is painted at that column's edge, floating
    // inside the page on a wide screen, with dead gutters either side.
    expect(viewport.className).not.toMatch(/max-w-/)
    expect(viewport.querySelector('.max-w-7xl')).not.toBeNull()
  })

  /**
   * Card renders `overflow-hidden`, which removes a flex item's automatic
   * minimum size; without this the cards on a page taller than the viewport
   * were squashed into slivers that clipped their own headers and buttons.
   */
  it('keeps the column from crushing its cards', () => {
    setup()
    const column = document.body.querySelector('.max-w-7xl')
    expect(column).not.toBeNull()
    expect(column.className).toContain('[&>*]:shrink-0')
  })
})
