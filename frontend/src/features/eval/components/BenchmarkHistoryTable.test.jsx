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
  started_at: '2026-08-26T20:15:00Z',
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

const QUEUED = {
  benchmark_id: 'bm-queued',
  dataset_name: 'golden_smoke_30',
  profile: 'smoke_quality',
  status: 'queued',
  created_at: '2026-08-26T21:30:00Z',
  phases: [{ name: 'end_to_end_regular', status: 'queued' }],
}

/** A run written before the timing fields existed carries none of them. */
const LEGACY = {
  benchmark_id: 'bm-legacy',
  dataset_name: 'golden_smoke_30',
  profile: 'smoke_quality',
  status: 'completed',
  phases: [{ name: 'end_to_end_regular', status: 'completed' }],
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
    for (const heading of ['Started', 'Profile', 'Dataset', 'Status', 'Total time', 'Key result']) {
      expect(screen.getByRole('columnheader', { name: heading })).toBeInTheDocument()
    }
  })

  it('shows the profile, dataset, total time and key result of a run', () => {
    setup([COMPLETED])
    const row = screen.getAllByRole('row')[1]
    expect(within(row).getByText('Full Quality')).toBeInTheDocument()
    expect(within(row).getByText(/golden_smoke_30 · v2/)).toBeInTheDocument()
    expect(within(row).getByText('Completed')).toBeInTheDocument()
    // Creation to finish: the wait as the person who pressed the button
    // experienced it, not the 1m 41s the worker was busy for.
    expect(within(row).getByText('2m 41s')).toBeInTheDocument()
    expect(within(row).queryByText('1m 41s')).not.toBeInTheDocument()
    expect(within(row).getByText('MRR 0.81')).toBeInTheDocument()
  })

  it('puts the actual start time under Started, never the creation time', () => {
    setup([COMPLETED])
    const started = within(screen.getAllByRole('row')[1]).getAllByRole('cell')[0]
    const time = (iso) =>
      new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }).format(Date.parse(iso))
    expect(started).toHaveTextContent(time(COMPLETED.started_at))
    expect(started).not.toHaveTextContent(time(COMPLETED.created_at))
  })

  it('says a run that has not started is queued rather than calling it started', () => {
    setup([QUEUED])
    const started = within(screen.getAllByRole('row')[1]).getAllByRole('cell')[0]
    expect(started).toHaveTextContent(/^Queued /)
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
    expect(within(row).queryByText('MRR 0.00')).not.toBeInTheDocument()
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

  it('renders a legacy run with no timestamps as dashes, never as zero', () => {
    setup([LEGACY])
    const cells = within(screen.getAllByRole('row')[1]).getAllByRole('cell')
    expect(cells[0]).toHaveTextContent('—')
    expect(cells[4]).toHaveTextContent('—')
    expect(cells[4]).not.toHaveTextContent('0m 00s')
  })

  it('explains an empty history clearly', () => {
    setup([])
    expect(screen.getByText(/No benchmark runs yet/)).toBeInTheDocument()
  })
})
