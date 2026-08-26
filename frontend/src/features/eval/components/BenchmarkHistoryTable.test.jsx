/**
 * Tests for the compact benchmark history.
 *
 * History used to be stacked cards with a benchmark id as their most
 * prominent line. It is a table now, and the id is a tooltip: these cover
 * that the columns carry the facts that distinguish two runs, and that a
 * duration nobody recorded still reads as a dash.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import BenchmarkHistoryTable from './BenchmarkHistoryTable'

const COMPLETED = {
  benchmark_id: 'bm-01HQ8Z7W6M4KP0V2X9RC3TJ5AB',
  dataset_name: 'golden_smoke_30',
  dataset_version: 2,
  profile: 'full_quality',
  status: 'completed',
  created_at: '2026-08-26T20:14:00Z',
  started_at: '2026-08-26T20:14:00Z',
  finished_at: '2026-08-26T20:16:41Z',
  phases: [{ name: 'retrieval_base', status: 'completed', results: { mrr: 0.812 } }],
}

const RUNNING = {
  benchmark_id: 'bm-running',
  dataset_name: 'golden_smoke_30',
  profile: 'smoke_quality',
  status: 'running',
  created_at: '2026-08-26T21:00:00Z',
  phases: [{ name: 'end_to_end_regular', status: 'running' }],
}

function setup(history = [COMPLETED, RUNNING], props = {}) {
  const onSelect = vi.fn()
  const onDownload = vi.fn()
  render(
    <BenchmarkHistoryTable
      history={history}
      selectedId="bm-running"
      busy={false}
      onSelect={onSelect}
      onDownload={onDownload}
      {...props}
    />
  )
  return { onSelect, onDownload }
}

describe('BenchmarkHistoryTable', () => {
  it('names its columns rather than stacking free text', () => {
    setup()
    for (const heading of ['Started', 'Profile', 'Dataset', 'Status', 'Duration', 'Key result']) {
      expect(screen.getByRole('columnheader', { name: heading })).toBeInTheDocument()
    }
  })

  it('shows the profile, dataset, duration and key result of a run', () => {
    setup([COMPLETED])
    const row = screen.getAllByRole('row')[1]
    expect(within(row).getByText('Full Quality')).toBeInTheDocument()
    expect(within(row).getByText(/golden_smoke_30 · v2/)).toBeInTheDocument()
    expect(within(row).getByText('Completed')).toBeInTheDocument()
    expect(within(row).getByText('2m 41s')).toBeInTheDocument()
    expect(within(row).getByText('MRR 0.812')).toBeInTheDocument()
  })

  it('keeps the benchmark id out of the row body and in its title', () => {
    setup([COMPLETED])
    const row = screen.getAllByRole('row')[1]
    expect(row).toHaveAttribute('title', COMPLETED.benchmark_id)
    expect(row.textContent).not.toContain(COMPLETED.benchmark_id)
  })

  it('renders a run with no result yet as a dash, never as zero', () => {
    setup([RUNNING])
    const row = screen.getAllByRole('row')[1]
    expect(within(row).getAllByText('—').length).toBeGreaterThan(0)
    expect(within(row).queryByText('MRR 0.000')).not.toBeInTheDocument()
  })

  it('selects a run and downloads a terminal one by id', async () => {
    const user = userEvent.setup()
    const { onSelect, onDownload } = setup()

    await user.click(screen.getByRole('button', { name: /^View Full Quality started/ }))
    expect(onSelect).toHaveBeenCalledWith(COMPLETED.benchmark_id)

    await user.click(screen.getByRole('button', { name: /^Download Full Quality started/ }))
    expect(onDownload).toHaveBeenCalledWith(COMPLETED.benchmark_id)
  })

  it('offers no archive for a run that has not reached a terminal state', () => {
    setup([RUNNING])
    expect(screen.queryByRole('button', { name: /^Download/ })).not.toBeInTheDocument()
  })

  it('cannot re-select the run already on screen', () => {
    setup()
    expect(screen.getByRole('button', { name: /^View Smoke Quality started/ })).toBeDisabled()
  })

  it('explains an empty history clearly', () => {
    setup([])
    expect(screen.getByText(/No benchmark runs yet/)).toBeInTheDocument()
  })
})
