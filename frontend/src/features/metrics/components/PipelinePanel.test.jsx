/**
 * Tests for the ingestion pipeline panel.
 *
 * The panel takes its data as props, so these render it directly rather than
 * mocking the hook — `MetricsTab.test.jsx` already covers the hook wiring.
 *
 * Two behaviours here are deliberate choices rather than incidental rendering,
 * and are pinned so a later simplification cannot quietly undo them: an empty
 * stuck-file list reads as calm rather than as an alert, and a window with no
 * uploads still renders if something is stuck.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import PipelinePanel from './PipelinePanel'

const FUNNEL_STEPS = [
  { step: 'uploaded', count: 100, dropped: null, drop_off: null, share_of_uploaded: 1 },
  { step: 'extracted', count: 90, dropped: 10, drop_off: 0.1, share_of_uploaded: 0.9 },
  { step: 'chunked', count: 80, dropped: 10, drop_off: 0.1111, share_of_uploaded: 0.8 },
  { step: 'embedded', count: 40, dropped: 40, drop_off: 0.5, share_of_uploaded: 0.4 },
  { step: 'indexed', count: 40, dropped: 0, drop_off: 0, share_of_uploaded: 0.4 },
]

function build(overrides = {}) {
  const { ingestion, ...rest } = overrides
  return {
    ingestion: {
      funnel: { files: 100, funnel_steps: FUNNEL_STEPS, stage_completion: [] },
      task_durations: { tasks: 12, mean_seconds: 30, p95_seconds: 90, p99_seconds: 120 },
      stuck_files: { count: 0, threshold_minutes: 30, files: [], truncated: false },
      ...(ingestion || {}),
    },
    cost: {
      by_model: [
        { model: 'local-model', turns: 12, tokens_in: 5000, tokens_out: 900, estimated_cost_usd: 0 },
      ],
      by_tenant: [{ tenant_id: 'tenant-a', turns: 12, tokens_in: 5000, tokens_out: 900 }],
      tokens_in: 5000,
      tokens_out: 900,
      estimated_cost_usd: 0,
      models_without_pricing: [],
    },
    file_processing_p95_seconds: { chunking: 1.5 },
    embedding_p95_seconds: 0.12,
    embedding_chunk_rate: 8.4,
    kafka_consumer_lag: [{ topic: 'file_events', group: 'files_grp', value: 42 }],
    dlq_rate: [],
    vectors: {
      scope: 'all_tenants',
      collections: [{ collection: 'documents', vectors: 12000 }],
      growth: { documents: 250 },
    },
    ...rest,
  }
}

describe('PipelinePanel', () => {
  it('renders the funnel with counts and server-computed drop-off', () => {
    render(<PipelinePanel data={build()} />)

    expect(screen.getByText('Ingestion funnel')).toBeInTheDocument()
    expect(screen.getByText('Uploaded')).toBeInTheDocument()
    expect(screen.getByText('Indexed')).toBeInTheDocument()
    // Half were lost between chunked and embedded.
    expect(screen.getByText(/50%/)).toBeInTheDocument()
    // Bars are the shared ProgressBar primitive, not a new component.
    expect(screen.getAllByRole('progressbar')).toHaveLength(5)
  })

  it('gives the first funnel step no drop-off rather than 0%', () => {
    render(<PipelinePanel data={build()} />)

    // `uploaded` has nothing before it, so rendering "0%" would claim a
    // measurement that was never made.
    const uploaded = screen.getByText('Uploaded').closest('li')
    expect(uploaded.textContent).not.toMatch(/%/)
  })

  it('renders zero stuck files as a calm neutral state', () => {
    render(<PipelinePanel data={build()} />)

    // An empty stuck-list is the healthy case and must not look like an alert.
    expect(
      screen.getByText(/Nothing has been in flight longer than 30 minutes/)
    ).toBeInTheDocument()
    expect(screen.queryByText('Stuck files')).not.toBeInTheDocument()
  })

  it('lists stuck files when there are any', () => {
    render(
      <PipelinePanel
        data={build({
          ingestion: {
            funnel: { files: 100, funnel_steps: FUNNEL_STEPS },
            stuck_files: {
              count: 2,
              threshold_minutes: 30,
              truncated: false,
              files: [
                { file_id: 'f-1', filename: 'report.pdf', status: 'processing' },
                { file_id: 'f-2', filename: 'notes.docx', status: 'resuming' },
              ],
            },
          },
        })}
      />
    )

    expect(screen.getByText('Stuck files')).toBeInTheDocument()
    expect(screen.getByText('report.pdf')).toBeInTheDocument()
    expect(screen.getByText('notes.docx')).toBeInTheDocument()
  })

  it('labels every cost as an estimate', () => {
    render(<PipelinePanel data={build()} />)

    expect(screen.getByText(/not billed amounts/)).toBeInTheDocument()
    expect(screen.getByText('estimate')).toBeInTheDocument()
  })

  it('says an unpriced model is unpriced rather than free', () => {
    render(
      <PipelinePanel
        data={build({
          cost: {
            by_model: [
              { model: 'local-model', turns: 1, tokens_in: 10, tokens_out: 5, estimated_cost_usd: 0 },
            ],
            by_tenant: [],
            tokens_in: 10,
            tokens_out: 5,
            estimated_cost_usd: 0,
            models_without_pricing: ['local-model'],
          },
        })}
      />
    )

    // The $0.00 trap: a zero total beside models that simply have no price.
    expect(screen.getByText(/means unpriced, not free/)).toBeInTheDocument()
  })

  it('distinguishes no consumer-lag series from a lag of zero', () => {
    render(<PipelinePanel data={build({ kafka_consumer_lag: [] })} />)

    expect(
      screen.getByText(/No consumer group has reported an offset yet/)
    ).toBeInTheDocument()
  })

  it('shows vector counts and what the window added', () => {
    render(<PipelinePanel data={build()} />)

    expect(screen.getByText('documents')).toBeInTheDocument()
    expect(screen.getByText('12,000')).toBeInTheDocument()
    expect(screen.getByText('250')).toBeInTheDocument()
  })

  it('renders an empty state when nothing was ingested and nothing is stuck', () => {
    render(
      <PipelinePanel
        data={{
          ingestion: {
            funnel: { files: 0, funnel_steps: [] },
            stuck_files: { count: 0, threshold_minutes: 30, files: [] },
          },
        }}
      />
    )

    expect(screen.getByText('No ingestion activity')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/NaN/)
  })

  it('still renders when files are stuck but the window is empty', () => {
    // `stuck_files` is deliberately not window-scoped: a file wedged last week
    // must not be hidden behind a quiet 1h window.
    render(
      <PipelinePanel
        data={{
          ingestion: {
            funnel: { files: 0, funnel_steps: [] },
            stuck_files: {
              count: 1,
              threshold_minutes: 30,
              files: [{ file_id: 'f-9', filename: 'wedged.pdf', status: 'processing' }],
            },
          },
        }}
      />
    )

    expect(screen.queryByText('No ingestion activity')).not.toBeInTheDocument()
    expect(screen.getByText('wedged.pdf')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/NaN/)
  })

  it('degrades only the Prometheus widgets when the store is down', () => {
    render(<PipelinePanel data={build()} promAvailable={false} />)

    expect(screen.getAllByText(/Metrics store unavailable/i).length).toBeGreaterThan(0)
    // The MongoDB-backed funnel is untouched by a Prometheus outage.
    expect(screen.getByText('Uploaded')).toBeInTheDocument()
    expect(screen.getAllByRole('progressbar')).toHaveLength(5)
  })

  it('renders an error state with a retry action', () => {
    const onRetry = vi.fn()
    render(<PipelinePanel error="Gateway timeout" onRetry={onRetry} />)

    expect(screen.getByText('Could not load pipeline metrics')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })
})
