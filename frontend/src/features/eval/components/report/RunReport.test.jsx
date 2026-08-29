/**
 * Tests for the run report surface.
 *
 * These carry over the evidence semantics the old panel was tested on — a
 * stale label is not a retrieval miss, an absent measurement is a dash — and
 * add what the report structure could plausibly have broken: a warning must
 * never sit behind a tab, a skipped stage must not read as a failure, a
 * comparison must declare itself invalid before it shows a delta, and the
 * raw exception must stay under Technical details.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import RunReport from './RunReport'
import { benchmarkReport, evaluationReport } from '../../runReport'

const SHA = '20b2ea7875df9e04c54d0b8af98f5ea6a96b764b0169a7763d01aa51b2887b3e'
const DATASET = { dataset_id: 'd-1', name: 'golden_smoke_30', dataset_sha256: SHA, item_count: 30 }

const MANIFEST = {
  dataset: { phases: ['retrieval_base'] },
  chunking: { size: 800 },
  vector_store: { collection: 'c' },
  embedding: { model: 'e5' },
  llm: { model: 'qwen' },
  retrieval: { top_k: 6 },
}

const RESULTS = {
  recall_at_k: { 1: 0.5, 3: 0.75, 5: 1, 10: 1, 20: 1 },
  precision_at_k: { 1: 0.5, 3: 0.25, 5: 0.2, 10: 0.1, 20: 0.05 },
  hit_rate_at_k: { 1: 0.5, 3: 1, 5: 1, 10: 1, 20: 1 },
  ndcg_at_k: { 1: 0.5, 3: 0.8, 5: 0.85, 10: 0.87, 20: 0.87 },
  mrr: 0.75,
  items_evaluated: 20,
  items_skipped: 0,
  items_unscorable: 0,
  items_failed: 0,
  mean_latency_ms: 120,
  failure_attribution: {
    items_attributed: 10,
    items_without_failure: 8,
    items_unclassified: 0,
    counts: { ranking: 2 },
    rates: { ranking: 0.2 },
  },
}

const RUN = {
  run_id: 'r-2',
  status: 'completed',
  mode: 'retrieval',
  match_mode: 'chunk_id',
  dataset_version: 2,
  dataset_sha256: SHA,
  started_at: '2026-08-26T10:00:00Z',
  finished_at: '2026-08-26T10:01:00Z',
  config_snapshot: { top_k_documents: 6, reranker_active: false, unobserved: ['embedding_model'] },
  results: RESULTS,
  per_item: [
    {
      item_id: 'i-1',
      query: 'found first',
      reciprocal_rank: 1,
      first_hit_rank: 1,
      recall_at_10: 1,
      outcome: 'success',
      latency_ms: 100,
      expected_ids: ['c1'],
      retrieved_ids: ['c1'],
    },
    {
      item_id: 'i-2',
      query: 'never found',
      reciprocal_rank: 0,
      first_hit_rank: null,
      recall_at_10: 0,
      outcome: 'success',
      latency_ms: 300,
      expected_ids: ['c9'],
      retrieved_ids: ['c3'],
      failure_attribution: { category: 'ranking' },
    },
  ],
}

function benchmark(overrides = {}) {
  return {
    benchmark_id: 'b-2',
    profile: 'full_quality',
    status: 'completed',
    created_at: '2026-08-26T12:00:00Z',
    started_at: '2026-08-26T12:00:00Z',
    finished_at: '2026-08-26T12:04:00Z',
    dataset_id: 'd-1',
    dataset_name: 'golden_smoke_30',
    dataset_version: 2,
    dataset_sha256: SHA,
    manifest: MANIFEST,
    progress: { items_per_phase: 30 },
    phases: [
      { name: 'retrieval_base', status: 'completed', results: { ...RESULTS } },
      { name: 'end_to_end_regular', status: 'completed', results: { ...RESULTS, mrr: 0.6 } },
    ],
    ...overrides,
  }
}

function renderEvaluation(run = RUN, props = {}) {
  return render(
    <RunReport report={evaluationReport(run, DATASET)} dataset={DATASET} runs={[run]} {...props} />
  )
}

function renderBenchmark(record = benchmark(), props = {}) {
  return render(
    <RunReport report={benchmarkReport(record, DATASET)} dataset={DATASET} {...props} />
  )
}

async function openTab(user, name) {
  await user.click(screen.getByRole('tab', { name: new RegExp(name, 'i') }))
}

describe('run header', () => {
  it('names the run by profile, dataset and time rather than by its id', () => {
    renderBenchmark()
    const heading = screen.getByRole('heading', { name: /Full Quality/ })
    expect(heading).toBeInTheDocument()
    expect(screen.getByText(/golden_smoke_30 · v2 · 30 items · started/)).toBeInTheDocument()
    // The id is still on the page, as metadata rather than as the title.
    expect(heading).not.toHaveTextContent('b-2')
    expect(screen.getByText('b-2')).toBeInTheDocument()
  })

  it('renders nothing at all without a run', () => {
    const { container } = render(<RunReport report={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('execution flow', () => {
  it('explains a downstream stage as skipped, never as failed', () => {
    renderBenchmark(
      benchmark({
        status: 'failed',
        error: 'Vector store unavailable',
        phases: [
          { name: 'retrieval_base', status: 'failed', error: 'Vector store unavailable' },
          { name: 'end_to_end_regular', status: 'queued' },
        ],
      })
    )
    const flow = screen.getByRole('list', { name: 'Execution flow' })
    expect(within(flow).getByText('Skipped')).toBeInTheDocument()
    expect(within(flow).getAllByText('Failed')).toHaveLength(1)
    expect(screen.getByText(/Not run: Retrieval baseline failed first/)).toBeInTheDocument()
  })

  it('reads an unsupported phase as unsupported, not as a failure', () => {
    renderBenchmark(
      benchmark({
        phases: [
          { name: 'retrieval_base', status: 'completed', results: RESULTS },
          { name: 'end_to_end_extended', status: 'unsupported', reason: 'No graph on this build' },
        ],
      })
    )
    const flow = screen.getByRole('list', { name: 'Execution flow' })
    expect(within(flow).getByText('Not supported')).toBeInTheDocument()
    expect(within(flow).queryByText('Failed')).not.toBeInTheDocument()
  })
})

describe('failure UX', () => {
  const FAILED = benchmark({
    status: 'failed',
    error: 'ConnectionError: vector store unavailable at qdrant:6333',
    phases: [
      { name: 'retrieval_base', status: 'failed', error: 'vector store unavailable' },
      { name: 'end_to_end_regular', status: 'queued' },
    ],
  })

  it('leads with product copy and keeps the exception under technical details', async () => {
    const user = userEvent.setup()
    renderBenchmark(FAILED)

    expect(screen.getByText('The run stopped after an error')).toBeInTheDocument()
    expect(
      screen.getByText(/Retrieval baseline failed while the run was executing/)
    ).toBeInTheDocument()
    expect(screen.getByText(/End-to-end never ran/)).toBeInTheDocument()

    const raw = screen.getByText(/ConnectionError: vector store unavailable/)
    expect(raw.closest('details')).not.toBeNull()
    expect(raw.closest('details').open).toBe(false)

    await user.click(screen.getByText('Technical details'))
    expect(raw.closest('details').open).toBe(true)
  })

  it('never hides a failure behind a tab', () => {
    renderBenchmark(FAILED)
    expect(
      screen.getByText('The run stopped after an error').closest('[role="tabpanel"]')
    ).toBeNull()
  })

  it('offers a retry only when the page can actually start one', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const { unmount } = renderBenchmark(FAILED, { onRetry })
    await user.click(screen.getByRole('button', { name: 'Retry run' }))
    expect(onRetry).toHaveBeenCalled()

    unmount()
    renderBenchmark(FAILED)
    expect(screen.queryByRole('button', { name: 'Retry run' })).not.toBeInTheDocument()
  })

  it('never hides a stale-label warning behind a tab', () => {
    renderEvaluation({
      ...RUN,
      label_validation: {
        checked: true,
        stale_label_count: 3,
        stale_item_count: 2,
        stale_ids: ['c9'],
      },
    })
    const warning = screen.getByText('Benchmark labels no longer exist')
    expect(warning.closest('[role="tabpanel"]')).toBeNull()
    expect(screen.getByText(/not retrieval misses/i)).toBeInTheDocument()
  })
})

describe('KPI summary', () => {
  it('states each headline figure with the sample behind it', () => {
    renderEvaluation()
    expect(screen.getByText('MRR')).toBeInTheDocument()
    expect(screen.getByText('0.75')).toBeInTheDocument()
    expect(screen.getByText(/mean reciprocal rank over 20 scored items/)).toBeInTheDocument()
    // Percentiles come from the run's own per-item latencies, with the sample.
    expect(screen.getByText('Latency p95')).toBeInTheDocument()
    expect(screen.getByText(/over 2 queries/)).toBeInTheDocument()
  })

  it('renders an unmeasured figure as a dash, never as NaN or a zero', () => {
    renderEvaluation({ ...RUN, results: { items_evaluated: 3 }, per_item: [] })
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3)
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument()
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
  })
})

describe('report tabs', () => {
  it('opens the retrieval evidence only when it is asked for', async () => {
    const user = userEvent.setup()
    renderEvaluation()
    expect(screen.queryByRole('table', { name: /scores at each cutoff/i })).not.toBeInTheDocument()

    await openTab(user, 'Retrieval')
    const table = screen.getByRole('table', { name: /scores at each cutoff/i })
    expect(within(table).getByText('Recall@k')).toBeInTheDocument()
    expect(within(table).getByText('75%')).toBeInTheDocument()
  })

  it('says a retrieval run produced no answers rather than showing an empty quality tab', async () => {
    const user = userEvent.setup()
    renderEvaluation()
    await openTab(user, 'Quality')
    expect(screen.getByText(/generated no answers/i)).toBeInTheDocument()
  })

  it('lists only the stages that actually lost items', async () => {
    const user = userEvent.setup()
    renderEvaluation()
    await openTab(user, 'Failures')
    expect(screen.getByText('Ranked out of the context')).toBeInTheDocument()
    expect(screen.queryByText('Never a candidate')).not.toBeInTheDocument()
  })

  it('shows the configuration the run scored under', async () => {
    const user = userEvent.setup()
    renderEvaluation()
    await openTab(user, 'Configuration')
    expect(screen.getByText('Top-k documents')).toBeInTheDocument()
    // Booleans read as words, not as true/false.
    expect(screen.getByText('Off')).toBeInTheDocument()
  })

  it('keeps every wide table inside its own scroller', async () => {
    const user = userEvent.setup()
    renderEvaluation()
    for (const name of ['Retrieval', 'Failures', 'Items', 'Configuration']) {
      await openTab(user, name)
      for (const table of screen.getAllByRole('table')) {
        expect(table.closest('.overflow-x-auto')).not.toBeNull()
      }
    }
  })
})

describe('items tab', () => {
  it('puts the worst rows first and filters them by band, failure and text', async () => {
    const user = userEvent.setup()
    renderEvaluation()
    await openTab(user, 'Items')

    const rows = within(screen.getByRole('table', { name: /per-item/i })).getAllByRole('row')
    expect(rows[1]).toHaveTextContent('never found')
    expect(rows[1]).toHaveTextContent('Ranked out of the context')
    expect(rows[2]).toHaveTextContent('found first')

    await user.type(screen.getByLabelText('Search items'), 'found first')
    expect(screen.getByText('1 of 2 items')).toBeInTheDocument()
    expect(screen.queryByText('never found')).not.toBeInTheDocument()

    await user.clear(screen.getByLabelText('Search items'))
    await user.click(screen.getByRole('button', { name: 'Failures only' }))
    // A retrieval miss is not an execution failure, so nothing matches.
    expect(screen.getByText('No item matches these filters.')).toBeInTheDocument()
  })

  it('sends a benchmark reader to the archive rather than showing an empty table', async () => {
    const user = userEvent.setup()
    renderBenchmark()
    await openTab(user, 'Items')
    expect(screen.getByText(/diagnostic archive/i)).toBeInTheDocument()
  })
})

describe('comparison integrity', () => {
  const BASELINE = benchmark({
    benchmark_id: 'b-1',
    created_at: '2026-08-25T12:00:00Z',
    manifest: { ...MANIFEST, embedding: { model: 'other-model' } },
  })

  it('declares two differently configured runs not comparable before showing any delta', async () => {
    const user = userEvent.setup()
    renderBenchmark(benchmark(), { history: [BASELINE] })

    const banner = screen.getByText('Not directly comparable')
    expect(banner).toBeInTheDocument()
    expect(screen.getByText('Embedding')).toBeInTheDocument()

    // The verdict is rendered above the deltas it qualifies.
    const table = screen.getByRole('table', { name: /metric deltas/i })
    expect(banner.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await user.click(screen.getByRole('tab', { name: /Overview/ }))
  })

  it('says plainly when there is no baseline at all', () => {
    renderBenchmark()
    expect(screen.getByText(/No earlier run is available/i)).toBeInTheDocument()
  })
})
