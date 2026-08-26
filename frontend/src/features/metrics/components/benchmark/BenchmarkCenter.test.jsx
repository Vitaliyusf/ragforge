import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

const { mockUseBenchmarkRuns } = vi.hoisted(() => ({ mockUseBenchmarkRuns: vi.fn() }))
vi.mock('../../hooks/useBenchmarkRuns', () => ({ useBenchmarkRuns: mockUseBenchmarkRuns }))

import BenchmarkCenter from './BenchmarkCenter'

function setup(benchmark = null, overrides = {}) {
  const state = { benchmark, history: [], error: null, busy: false, start: vi.fn(), select: vi.fn(), download: vi.fn(), ...overrides }
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
    mockUseBenchmarkRuns.mockReturnValue({ benchmark: null, history: [], error: null, busy: false, start: vi.fn(), select: vi.fn(), download: vi.fn() })
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
    // Not the click event: download() treats its argument as a benchmark id.
    expect(state.download).toHaveBeenCalledWith()
  })

  it('shows live phase progress and prevents another full run', () => {
    setup({ benchmark_id: 'b-1', status: 'running', progress: { completed_phases: 1, items_per_phase: 30 }, phases: [{ name: 'retrieval_base', status: 'completed', results: { mrr: 0.8, mean_latency_ms: 11 } }, { name: 'end_to_end_regular', status: 'running', item_progress: { items_completed: 18, items_succeeded: 15, items_guardrail_blocked: 2, items_failed: 1, items_in_flight: 3 } }, { name: 'retrieval_extended', status: 'unsupported' }] })
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

  it('renders newest-first history, selects terminal runs, and downloads by id', async () => {
    const user = userEvent.setup()
    const state = setup({ benchmark_id: 'active', status: 'running', progress: {}, phases: [] }, { history: [
      { benchmark_id: 'newest', dataset_name: 'A very long golden set name that must truncate safely', dataset_version: 3, status: 'completed', created_at: '2026-08-26T20:14:00Z', phases: [] },
      { benchmark_id: 'active', dataset_name: 'Smoke30', status: 'running', phases: [{ name: 'retrieval_base', status: 'running' }] },
      { benchmark_id: 'failed-run', dataset_name: 'Smoke30', status: 'failed', phases: [] },
    ] })
    expect(screen.getByText('Benchmark history')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('newest')
    expect(screen.getByText(/Current phase: Retrieval baseline/)).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'View' })[0])
    expect(state.select).toHaveBeenCalledWith('newest')
    await user.click(screen.getAllByRole('button', { name: 'Download ZIP' })[1])
    expect(state.download).toHaveBeenCalledWith('failed-run')
  })

  it('explains an empty history clearly', () => {
    setup()
    expect(screen.getByText(/No benchmark runs yet/)).toBeInTheDocument()
  })

  it('compares a candidate with the newest compatible baseline', () => {
    const provenance = {
      dataset: { phases: ['retrieval_base'] },
      chunking: { size: 500 }, vector_store: { type: 'qdrant' },
      embedding: { model: 'embed-v1' }, llm: { chat_model: 'model-v1' },
      retrieval: { top_k_documents: 10 },
    }
    const candidate = { benchmark_id: 'candidate', status: 'completed', created_at: '2026-08-26T12:00:00Z', dataset_id: 'dataset-1', dataset_version: 1, dataset_sha256: 'abc', manifest: provenance, phases: [{ name: 'retrieval_base', status: 'completed', results: { mrr: 0.75, mean_latency_ms: 12 } }] }
    const baseline = { ...candidate, benchmark_id: 'baseline', created_at: '2026-08-25T12:00:00Z', phases: [{ name: 'retrieval_base', status: 'completed', results: { mrr: 0.5, mean_latency_ms: 10 } }] }

    setup(candidate, { history: [candidate, baseline] })

    expect(screen.getByLabelText('Benchmark comparison')).toHaveTextContent('Baseline baseline → Candidate candidate')
    expect(screen.getByText('+50.00%')).toBeInTheDocument()
  })

  it('warns instead of comparing incompatible model provenance', () => {
    const candidate = { benchmark_id: 'candidate', status: 'completed', created_at: '2026-08-26T12:00:00Z', dataset_id: 'dataset-1', dataset_version: 1, dataset_sha256: 'abc', manifest: { dataset: { phases: [] }, chunking: {}, vector_store: {}, embedding: { model: 'v2' }, llm: {}, retrieval: {} }, phases: [] }
    const baseline = { ...candidate, benchmark_id: 'baseline', created_at: '2026-08-25T12:00:00Z', manifest: { ...candidate.manifest, embedding: { model: 'v1' } } }

    setup(candidate, { history: [candidate, baseline] })

    expect(screen.getByLabelText('Benchmark comparison')).toHaveTextContent(/No compatible baseline.*model compatibility/i)
  })
})
