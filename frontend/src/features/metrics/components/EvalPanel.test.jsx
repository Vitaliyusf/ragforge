/**
 * Tests for the eval panel.
 *
 * `useEvalRuns` is mocked, so these cover what the panel renders from a run
 * document rather than the polling behaviour behind it. The recurring
 * assertion is the same one the rest of the tab makes: an absent measurement
 * renders as `—`, never as `NaN%` or a confident `0%`.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

const { mockUseEvalRuns } = vi.hoisted(() => ({ mockUseEvalRuns: vi.fn() }))

vi.mock('@/features/metrics/hooks/useEvalRuns', () => ({
  useEvalRuns: mockUseEvalRuns,
  isRunning: (run) => Boolean(run?.run_id) && !['completed', 'failed'].includes(run?.status),
}))

import EvalPanel, {
  DatasetProvenance,
  LabelValidation,
  diffSnapshots,
  estimateDescription,
} from './EvalPanel'

const SNAPSHOT = {
  top_k_documents: 6,
  reranker_enabled: true,
  embedding_model: null,
  unobserved: ['embedding_model'],
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
}

const SHA = '20b2ea7875df9e04c54d0b8af98f5ea6a96b764b0169a7763d01aa51b2887b3e'

const COMPLETED_RUN = {
  run_id: 'r-2',
  dataset_id: 'd-1',
  dataset_version: 2,
  dataset_sha256: SHA,
  status: 'completed',
  started_at: '2026-08-25T10:00:00Z',
  match_mode: 'chunk_id',
  config_snapshot: SNAPSHOT,
  results: RESULTS,
  per_item: [
    {
      item_id: 'i-1',
      query: 'found first',
      reciprocal_rank: 1,
      first_hit_rank: 1,
      recall_at_10: 1,
      expected_ids: ['c1'],
      retrieved_ids: ['c1'],
    },
    {
      item_id: 'i-2',
      query: 'never found',
      reciprocal_rank: 0,
      first_hit_rank: null,
      recall_at_10: 0,
      expected_ids: ['c9'],
      retrieved_ids: ['c1'],
    },
  ],
}

const DATASETS = [
  {
    dataset_id: 'd-1',
    name: 'Support golden set',
    item_count: 20,
    dataset_version: 2,
    dataset_sha256: SHA,
    last_run_at: '2026-08-25T10:00:00Z',
  },
]

function setup(overrides = {}) {
  mockUseEvalRuns.mockReturnValue({
    datasets: DATASETS,
    datasetId: 'd-1',
    selectDataset: vi.fn(),
    runs: [COMPLETED_RUN],
    run: COMPLETED_RUN,
    running: false,
    loading: false,
    error: null,
    busy: false,
    startRun: vi.fn(),
    estimateRunCost: vi.fn(),
    createDataset: vi.fn(),
    deleteDataset: vi.fn(),
    refresh: vi.fn(),
    ...overrides,
  })
  return render(<EvalPanel />)
}

// ── Empty state ───────────────────────────────────────────────────────────

describe('EvalPanel without a dataset', () => {
  it('explains how to build a golden set rather than showing empty charts', () => {
    setup({ datasets: [], runs: [], run: null })

    expect(screen.getByText('No golden set yet')).toBeInTheDocument()
    expect(screen.getByText(/questions your users actually ask/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /import a dataset/i })).toBeInTheDocument()
  })

  it('shows no scores at all, rather than zeroes', () => {
    setup({ datasets: [], runs: [], run: null })

    expect(screen.queryByText('MRR')).not.toBeInTheDocument()
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
  })
})

// ── Results ───────────────────────────────────────────────────────────────

describe('EvalPanel results', () => {
  it('renders the headline scores with their denominator', () => {
    setup()

    expect(screen.getByText('MRR')).toBeInTheDocument()
    expect(screen.getByText('0.75')).toBeInTheDocument()
    expect(screen.getByText('nDCG@10')).toBeInTheDocument()
    expect(screen.getByText('0.87')).toBeInTheDocument()
    expect(screen.getByText('Items scored')).toBeInTheDocument()
    expect(screen.getByText('0 skipped, 0 unscorable, 0 failed')).toBeInTheDocument()
  })

  it('renders recall and precision across every k', () => {
    setup()

    const table = screen.getByRole('table', { name: /scores at each cutoff/i })
    const recallRow = within(table).getByRole('row', { name: /Recall@k/ })
    expect(within(recallRow).getByText('50%')).toBeInTheDocument()
    expect(within(recallRow).getAllByText('100%').length).toBe(3)
  })

  it('renders an unmeasured score as a dash, never as NaN%', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        results: {
          ...RESULTS,
          mrr: null,
          recall_at_k: { 1: null, 3: null, 5: null, 10: null, 20: null },
        },
      },
    })

    const table = screen.getByRole('table', { name: /scores at each cutoff/i })
    const recallRow = within(table).getByRole('row', { name: /Recall@k/ })
    expect(within(recallRow).getAllByText('—').length).toBe(5)
    expect(within(table).queryByText(/NaN/)).not.toBeInTheDocument()
  })

  it('warns that a file-level run scores more generously', () => {
    setup({ run: { ...COMPLETED_RUN, match_mode: 'file_id' } })

    expect(screen.getByText(/any chunk from a relevant file counts as a hit/)).toBeInTheDocument()
  })
})

// ── Running state ─────────────────────────────────────────────────────────

describe('EvalPanel while a run is executing', () => {
  const RUNNING_RUN = {
    ...COMPLETED_RUN,
    run_id: 'r-3',
    status: 'running',
    results: {},
    per_item: [{ item_id: 'i-1', query: 'q', reciprocal_rank: 1 }],
  }

  it('shows the in-progress state and its item count', () => {
    setup({ run: RUNNING_RUN, running: true })

    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText(/1 of 20 items/)).toBeInTheDocument()
  })

  it('disables the run button so a second run cannot be started', () => {
    setup({ run: RUNNING_RUN, running: true })

    expect(screen.getByRole('button', { name: /running/i })).toBeDisabled()
  })

  it('says the run costs nothing, because that is why it is safe to re-run', () => {
    setup({ run: RUNNING_RUN, running: true })

    expect(screen.getByText(/calls no language model/)).toBeInTheDocument()
  })

  it('surfaces the error of a failed run rather than a silent empty panel', () => {
    setup({
      run: { ...COMPLETED_RUN, status: 'failed', error: 'embedding unavailable' },
    })

    expect(screen.getByText(/embedding unavailable/)).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
  })
})

// ── Config diff ───────────────────────────────────────────────────────────

describe('EvalPanel config comparison', () => {
  const PREVIOUS = {
    ...COMPLETED_RUN,
    run_id: 'r-1',
    started_at: '2026-08-24T10:00:00Z',
    config_snapshot: { ...SNAPSHOT, top_k_documents: 3, reranker_enabled: false },
  }

  it('warns when the two most recent runs used different settings', () => {
    setup({ runs: [COMPLETED_RUN, PREVIOUS] })

    expect(screen.getByText('Configuration changed between runs')).toBeInTheDocument()
    expect(screen.getByText(/not a measure of retrieval quality alone/)).toBeInTheDocument()
    expect(screen.getByText('Top-k documents')).toBeInTheDocument()
    expect(screen.getByText('Reranker')).toBeInTheDocument()
  })

  it('renders booleans as words rather than true/false', () => {
    setup({ runs: [COMPLETED_RUN, PREVIOUS] })

    const table = screen.getByRole('table', { name: /configuration differences/i })
    expect(within(table).getByText('On')).toBeInTheDocument()
    expect(within(table).getByText('Off')).toBeInTheDocument()
  })

  it('names the settings that were never captured', () => {
    setup({ runs: [COMPLETED_RUN, PREVIOUS] })

    expect(screen.getByText(/Not captured/)).toBeInTheDocument()
    expect(screen.getByText(/Embedding model/)).toBeInTheDocument()
  })

  it('stays silent when the two runs agree', () => {
    setup({ runs: [COMPLETED_RUN, { ...COMPLETED_RUN, run_id: 'r-1' }] })

    expect(screen.queryByText('Configuration changed between runs')).not.toBeInTheDocument()
  })
})

// ── Per-item drill-down ───────────────────────────────────────────────────

describe('EvalPanel per-item table', () => {
  it('lists the failures first', () => {
    setup()

    const table = screen.getByRole('table', { name: /per-item retrieval results/i })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('never found')).toBeInTheDocument()
  })

  it('renders a missing rank as a dash', () => {
    setup()

    const table = screen.getByRole('table', { name: /per-item retrieval results/i })
    expect(within(table).getByText('—')).toBeInTheDocument()
  })

  it('marks an unlabelled item as excluded rather than as a failure', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        per_item: [{ item_id: 'i-3', query: 'unlabelled', skipped: true }],
      },
    })

    expect(screen.getByText(/excluded from every average/)).toBeInTheDocument()
  })
})

// ── History ───────────────────────────────────────────────────────────────

describe('EvalPanel run history', () => {
  it('explains itself rather than drawing a chart from one point', () => {
    setup()

    expect(screen.getByText(/Two completed runs are needed/)).toBeInTheDocument()
  })
})

// ── diffSnapshots ─────────────────────────────────────────────────────────

describe('diffSnapshots', () => {
  it('reports only the keys that differ', () => {
    const diff = diffSnapshots({ a: 1, b: 2 }, { a: 1, b: 3 })
    expect(diff).toEqual([{ key: 'b', current: 2, previous: 3 }])
  })

  it('treats a key present in only one snapshot as a difference', () => {
    expect(diffSnapshots({ a: 1 }, {})).toEqual([{ key: 'a', current: 1, previous: undefined }])
  })

  it('never compares the unobserved list itself', () => {
    // Two runs that both failed to capture the embedding model have not been
    // shown to share one, so `unobserved` is not a setting to diff.
    expect(diffSnapshots({ unobserved: ['x'] }, { unobserved: ['y'] })).toEqual([])
  })
})

// ── Run mode and its cost gate ────────────────────────────────────────────

/** Pick "End-to-end" from the Radix select, which is not a native <select>. */
async function selectEndToEnd() {
  await userEvent.click(screen.getByLabelText('Run mode'))
  await userEvent.click(await screen.findByRole('option', { name: 'End-to-end' }))
}

const ESTIMATE = {
  mode: 'end_to_end',
  item_count: 20,
  calls_per_item: 2,
  estimated_tokens_in: 48000,
  estimated_tokens_out: 8000,
  estimated_cost_usd: 0,
  model: 'some/model',
  model_priced: false,
}

// ── Dataset provenance ─────────────────────────────────────

describe('EvalPanel dataset provenance', () => {
  it('names the version and fingerprint of the labels the run scored', () => {
    setup()

    expect(screen.getByText(/Labels scored: version 2/)).toBeInTheDocument()
    // Abbreviated for reading, whole in the title so it can still be copied.
    const digest = screen.getByText('20b2ea7875df')
    expect(digest).toBeInTheDocument()
    expect(digest).toHaveAttribute('title', SHA)
  })

  it('warns when the dataset has been edited since the run', () => {
    setup({
      datasets: [{ ...DATASETS[0], dataset_version: 3, dataset_sha256: 'f'.repeat(64) }],
    })

    expect(screen.getByText(/dataset has been edited since this run/i)).toBeInTheDocument()
  })

  it('stays quiet while the run still matches the dataset', () => {
    setup()

    expect(screen.queryByText(/dataset has been edited since this run/i)).not.toBeInTheDocument()
  })

  it('says a pre-versioning run recorded nothing rather than borrowing the current labels', () => {
    setup({
      run: { ...COMPLETED_RUN, dataset_version: null, dataset_sha256: null },
    })

    expect(screen.getByText(/predates dataset versioning/i)).toBeInTheDocument()
    expect(screen.queryByText(/Labels scored/)).not.toBeInTheDocument()
  })
})

describe('DatasetProvenance', () => {
  it('compares against the dataset only when the dataset carries a fingerprint', () => {
    render(<DatasetProvenance run={COMPLETED_RUN} dataset={{ dataset_id: 'd-1' }} />)

    // A dataset that has not been migrated yet is unknown, not different.
    expect(screen.queryByText(/dataset has been edited/i)).not.toBeInTheDocument()
    expect(screen.getByText(/Labels scored: version 2/)).toBeInTheDocument()
  })
})

describe('EvalPanel run modes', () => {
  it('defaults to the free retrieval run and says so', () => {
    setup()

    expect(screen.getByText(/No model is called, so the run is free/)).toBeInTheDocument()
  })

  it('starts a retrieval run without a cost confirmation', async () => {
    const startRun = vi.fn()
    setup({ startRun })

    await userEvent.click(screen.getByRole('button', { name: /run evaluation/i }))

    expect(startRun).toHaveBeenCalledWith('retrieval')
    expect(screen.queryByText(/Start an end-to-end run\?/)).not.toBeInTheDocument()
  })

  it('prices an end-to-end run before starting it', async () => {
    const startRun = vi.fn()
    const estimateRunCost = vi.fn().mockResolvedValue(ESTIMATE)
    setup({ startRun, estimateRunCost })

    await selectEndToEnd()
    await userEvent.click(screen.getByRole('button', { name: /run evaluation/i }))

    await waitFor(() => expect(estimateRunCost).toHaveBeenCalledWith(20, 'end_to_end', null))
    // Nothing starts until the estimate has been shown and accepted.
    expect(startRun).not.toHaveBeenCalled()
    expect(await screen.findByText(/Start an end-to-end run/)).toBeInTheDocument()
  })

  it('runs end-to-end only after the estimate is confirmed', async () => {
    const startRun = vi.fn()
    setup({ startRun, estimateRunCost: vi.fn().mockResolvedValue(ESTIMATE) })

    await selectEndToEnd()
    await userEvent.click(screen.getByRole('button', { name: /run evaluation/i }))
    await userEvent.click(await screen.findByRole('button', { name: /run anyway/i }))

    expect(startRun).toHaveBeenCalledWith('end_to_end')
  })

  it('does not start the run when the estimate could not be fetched', async () => {
    const startRun = vi.fn()
    setup({ startRun, estimateRunCost: vi.fn().mockResolvedValue(null) })

    await selectEndToEnd()
    await userEvent.click(screen.getByRole('button', { name: /run evaluation/i }))

    await waitFor(() => expect(startRun).not.toHaveBeenCalled())
  })
})

describe('estimateDescription', () => {
  it('states the tokens, the cost, and that it is an estimate', () => {
    const text = estimateDescription({ ...ESTIMATE, model_priced: true })

    expect(text).toMatch(/20 items × 2 model calls/)
    expect(text).toMatch(/56,000 tokens/)
    expect(text).toMatch(/\$0\.00/)
  })

  it('says a zero cost means unpriced, not free', () => {
    expect(estimateDescription(ESTIMATE)).toMatch(/no configured price/)
  })
})

// ── End-to-end answer quality ─────────────────────────────────────────────

const ANSWER_QUALITY = {
  groundedness: { mean: 0.82, counted: 18, excluded: 2 },
  citation_precision: { mean: 0.9, counted: 12, excluded: 8 },
  citation_recall: { mean: 0.6, counted: 15, excluded: 5 },
  unsupported_claims: { mean: 0.4, counted: 18, excluded: 2 },
  hallucination_rate: 0.2,
  hallucination_severe_rate: 0.05,
  items_judged: 18,
  items_unjudged: 2,
}

describe('EvalPanel answer quality', () => {
  it('is absent for a retrieval-only run', () => {
    setup()

    expect(screen.queryByText('Answer quality')).not.toBeInTheDocument()
  })

  it('reports answer quality with the items each figure covers', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        mode: 'end_to_end',
        results: { ...RESULTS, answer_quality: ANSWER_QUALITY },
      },
    })

    expect(screen.getByText('Answer quality')).toBeInTheDocument()
    expect(screen.getByText('0.82')).toBeInTheDocument()
    expect(screen.getByText(/18 judged, 2 unjudged/)).toBeInTheDocument()
    expect(screen.getByText(/8 cited nothing/)).toBeInTheDocument()
  })

  it('renders unmeasured answer quality as dashes, not zeroes', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        mode: 'end_to_end',
        results: {
          ...RESULTS,
          answer_quality: {
            groundedness: { mean: null, counted: 0, excluded: 20 },
            citation_precision: { mean: null, counted: 0, excluded: 20 },
            citation_recall: { mean: null, counted: 0, excluded: 20 },
            unsupported_claims: { mean: null, counted: 0, excluded: 20 },
            hallucination_rate: null,
            hallucination_severe_rate: null,
            items_judged: 0,
            items_unjudged: 20,
          },
        },
      },
    })

    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})


// ── Stale golden-set labels ───────────────────────────────────────────────
//
// The distinction under test throughout: a retrieval miss means the chunk is
// there and was not ranked; a stale label means the chunk is gone and no
// retriever could have found it. A recall chart cannot tell them apart, so
// the panel has to.

const CLEAN_VALIDATION = {
  checked: true,
  reason: null,
  error: null,
  policy: 'fail',
  labels_checked: 20,
  stale_label_count: 0,
  stale_item_count: 0,
  stale_ids: [],
  stale_item_ids: [],
  unretrievable_label_count: 0,
  unretrievable_item_count: 0,
  unretrievable_ids: [],
  unscorable_item_count: 0,
  truncated: false,
}

const STALE_VALIDATION = {
  ...CLEAN_VALIDATION,
  stale_label_count: 2,
  stale_item_count: 2,
  stale_ids: ['chunk-old-1', 'chunk-old-2'],
  stale_item_ids: ['i-8', 'i-9'],
  unscorable_item_count: 2,
}

describe('EvalPanel stale label reporting', () => {
  it('says plainly that the affected items are not retrieval misses', () => {
    setup({ run: { ...COMPLETED_RUN, label_validation: STALE_VALIDATION } })

    expect(screen.getByText('Benchmark labels no longer exist')).toBeInTheDocument()
    expect(screen.getByText(/not retrieval misses/i)).toBeInTheDocument()
    expect(screen.getByText(/chunk-old-1, chunk-old-2/)).toBeInTheDocument()
  })

  it('reports the stale label and item counts', () => {
    setup({ run: { ...COMPLETED_RUN, label_validation: STALE_VALIDATION } })

    expect(screen.getByText('Stale labels')).toBeInTheDocument()
    expect(screen.getByText('Items affected')).toBeInTheDocument()
  })

  it('keeps a suppressed label apart from a deleted one', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        label_validation: {
          ...CLEAN_VALIDATION,
          unretrievable_label_count: 1,
          unretrievable_item_count: 1,
          unretrievable_ids: ['chunk-removed'],
          unscorable_item_count: 1,
        },
      },
    })

    expect(screen.getByText('Excluded from retrieval')).toBeInTheDocument()
    expect(screen.getByText(/Unreachable ids: chunk-removed/)).toBeInTheDocument()
  })

  it('warns when a run scored without its labels being verified', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        label_validation: {
          ...CLEAN_VALIDATION,
          checked: false,
          reason: 'unavailable',
          error: 'vector_db timed out',
          stale_label_count: null,
          stale_item_count: null,
        },
      },
    })

    expect(screen.getByText('Labels were not verified')).toBeInTheDocument()
    expect(screen.getByText(/vector store could not be reached/i)).toBeInTheDocument()
    expect(screen.getByText('vector_db timed out')).toBeInTheDocument()
  })

  it('confirms a clean check without shouting about it', () => {
    setup({ run: { ...COMPLETED_RUN, label_validation: CLEAN_VALIDATION } })

    expect(screen.getByText(/no score below is a missing label in disguise/i)).toBeInTheDocument()
    expect(screen.queryByText('Benchmark labels no longer exist')).not.toBeInTheDocument()
  })

  it('claims nothing for a run recorded before the check existed', () => {
    setup({ run: { ...COMPLETED_RUN, label_validation: null } })

    expect(screen.queryByText('Benchmark labels no longer exist')).not.toBeInTheDocument()
    expect(screen.queryByText('Labels were not verified')).not.toBeInTheDocument()
    expect(screen.queryByText(/missing label in disguise/i)).not.toBeInTheDocument()
  })

  it('surfaces the refusal of a run that was stopped for stale labels', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        status: 'failed',
        error: 'Refused before scoring: 2 item(s) reference golden-set labels the active index cannot return',
        results: {},
        per_item: [],
        label_validation: STALE_VALIDATION,
      },
    })

    expect(screen.getByText(/Refused before scoring/)).toBeInTheDocument()
    expect(screen.getByText('Benchmark labels no longer exist')).toBeInTheDocument()
  })
})

describe('EvalPanel per-item stale rows', () => {
  it('labels an unscorable row as a missing benchmark label, not a miss', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        label_validation: STALE_VALIDATION,
        per_item: [
          { item_id: 'i-4', query: 'label deleted', unscorable: true, expected_ids: ['c-old'] },
        ],
      },
    })

    expect(screen.getByText(/benchmark label no longer exists/i)).toBeInTheDocument()
  })

  it('sinks unscorable rows below the real retrieval failures', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        label_validation: STALE_VALIDATION,
        per_item: [
          { item_id: 'i-4', query: 'label deleted', unscorable: true },
          ...COMPLETED_RUN.per_item,
        ],
      },
    })

    const table = screen.getByRole('table', { name: /per-item retrieval results/i })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('never found')).toBeInTheDocument()
    expect(within(rows[2]).getByText('label deleted')).toBeInTheDocument()
  })

  it('counts unscorable items in the denominator line', () => {
    setup({
      run: {
        ...COMPLETED_RUN,
        label_validation: STALE_VALIDATION,
        results: { ...RESULTS, items_evaluated: 18, items_unscorable: 2 },
      },
    })

    expect(screen.getByText(/2 unscorable/)).toBeInTheDocument()
  })
})

describe('LabelValidation', () => {
  it('renders nothing at all without a validation record', () => {
    const { container } = render(<LabelValidation validation={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
