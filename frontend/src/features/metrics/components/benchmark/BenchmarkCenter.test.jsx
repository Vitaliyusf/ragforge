import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

const { mockUseBenchmarkRuns } = vi.hoisted(() => ({ mockUseBenchmarkRuns: vi.fn() }))
vi.mock('../../hooks/useBenchmarkRuns', () => ({ useBenchmarkRuns: mockUseBenchmarkRuns }))

import BenchmarkCenter from './BenchmarkCenter'

function setup(benchmark = null, overrides = {}) {
  const state = { benchmark, error: null, busy: false, start: vi.fn(), download: vi.fn(), ...overrides }
  mockUseBenchmarkRuns.mockReturnValue(state)
  render(<BenchmarkCenter datasetId="dataset-1" datasetName="Support" ready />)
  return state
}

describe('BenchmarkCenter', () => {
  it('confirms before starting the full benchmark', async () => {
    const user = userEvent.setup()
    const state = setup()
    await user.click(screen.getByRole('button', { name: /run full benchmark/i }))
    expect(screen.getByText(/end-to-end phases may call/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /start benchmark/i }))
    expect(state.start).toHaveBeenCalledOnce()
  })

  it('keeps the action blocked until a golden set is ready', () => {
    mockUseBenchmarkRuns.mockReturnValue({ benchmark: null, error: null, busy: false, start: vi.fn(), download: vi.fn() })
    render(<BenchmarkCenter datasetId="" ready={false} />)
    expect(screen.getByRole('button', { name: /run full benchmark/i })).toBeDisabled()
    expect(screen.getByText(/import and validate/i)).toBeInTheDocument()
  })

  it.each(['partial', 'failed'])('shows a terminal %s benchmark and allows its archive to download', async (status) => {
    const user = userEvent.setup()
    const state = setup({ benchmark_id: 'b-1', status, progress: { completed_phases: 1, total_phases: 4 }, phases: [], error: status === 'failed' ? 'Vector store unavailable' : null })
    expect(screen.getByText('Benchmark Run: 1 / 4 executable phases complete')).toBeInTheDocument()
    if (status === 'failed') expect(screen.getByText('Vector store unavailable')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /download diagnostic zip/i }))
    expect(state.download).toHaveBeenCalledOnce()
  })

  it('shows live phase progress and prevents another full run', () => {
    setup({ benchmark_id: 'b-1', status: 'running', progress: { completed_phases: 1 }, phases: [{ name: 'retrieval_base', status: 'completed', results: { mrr: 0.8, mean_latency_ms: 11 } }, { name: 'end_to_end_regular', status: 'running', item_progress: { items_total: 30, items_completed: 18, items_succeeded: 15, items_guardrail_blocked: 2, items_failed: 1, items_in_flight: 3 } }, { name: 'retrieval_extended', status: 'unsupported' }] })
    expect(screen.getByText('Retrieval baseline')).toBeInTheDocument()
    expect(screen.getAllByText('End-to-end')).toHaveLength(2)
    expect(screen.getByText(/Retrieval baseline: MRR 0.800, mean latency 11 ms/)).toBeInTheDocument()
    expect(screen.getByText('Benchmark Run: 1 / 2 executable phases complete')).toBeInTheDocument()
    expect(screen.getByText(/18\s*\/\s*30\s+60%/)).toBeInTheDocument()
    expect(screen.getByText('Guardrail blocked')).toBeInTheDocument()
    expect(screen.getByText(/safe to leave this page/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /benchmark running/i })).toBeDisabled()
  })

  it('keeps dataset, run, and export terminology distinct', () => {
    setup({ benchmark_id: 'b-1', status: 'completed', progress: {}, phases: [] })
    expect(screen.getByText(/Golden Set \/ Dataset: Support/)).toBeInTheDocument()
    expect(screen.getByText(/Benchmark Run:/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /diagnostic zip/i })).toBeInTheDocument()
  })
})
