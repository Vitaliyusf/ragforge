/**
 * Tests for the eval result surface.
 *
 * These carry over the evidence semantics the old panel was tested on — an
 * absent measurement is a dash and never a confident zero, a stale label is
 * not a retrieval miss — and add the one thing progressive disclosure could
 * plausibly have broken: warnings must not be hidden behind an accordion.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import EvalResults, {
  DatasetProvenance,
  FailureAttribution,
  LabelValidation,
  diffSnapshots,
  failureLabel,
} from './EvalResults'

const SNAPSHOT = {
  snapshot_version: 2,
  top_k_documents: 6,
  reranker_active: false,
  pass_two_active: true,
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

const RUN = {
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
      retrieved_ids: ['c3'],
      failure_attribution: { category: 'ranking' },
    },
  ],
}

const DATASET = { dataset_id: 'd-1', name: 'golden_smoke_30', dataset_sha256: SHA }

/** Disclosure sections are collapsed by design; open one to read it. */
async function open(user, title) {
  await user.click(screen.getByText(title))
}

describe('EvalResults headline scores', () => {
  it('renders the headline scores with their denominator', () => {
    render(<EvalResults run={RUN} runs={[RUN]} dataset={DATASET} />)
    expect(screen.getByText('MRR')).toBeInTheDocument()
    expect(screen.getByText('0.75')).toBeInTheDocument()
    expect(screen.getByText('Recall@5')).toBeInTheDocument()
    expect(screen.getAllByText('100%').length).toBeGreaterThan(0)
    expect(screen.getByText('Items scored')).toBeInTheDocument()
    expect(screen.getByText(/0 skipped, 0 unscorable, 0 failed/)).toBeInTheDocument()
  })

  it('renders an unmeasured score as a dash, never as NaN% or zero', () => {
    render(
      <EvalResults
        run={{ ...RUN, per_item: [], results: { items_evaluated: 3 } }}
        runs={[]}
        dataset={DATASET}
      />
    )
    // Every headline figure the run did not measure — MRR, Recall@5, nDCG,
    // latency — reads as a dash. A measured zero elsewhere is a real zero;
    // an absent measurement must never borrow its confidence.
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4)
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument()
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
    expect(screen.queryByText('0.00')).not.toBeInTheDocument()
  })

  it('renders nothing at all without a run', () => {
    const { container } = render(<EvalResults run={null} runs={[]} dataset={DATASET} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('reports answer quality only for a run that produced answers', () => {
    const { rerender } = render(<EvalResults run={RUN} runs={[RUN]} dataset={DATASET} />)
    expect(screen.queryByText('Mean groundedness')).not.toBeInTheDocument()

    rerender(
      <EvalResults
        run={{
          ...RUN,
          results: {
            ...RESULTS,
            answer_quality: {
              groundedness: { mean: 0.91, counted: 18 },
              citation_precision: { mean: 0.8, excluded: 2 },
              citation_recall: { mean: null, counted: 0 },
              hallucination_rate: 0.05,
              items_judged: 18,
              items_unjudged: 2,
            },
          },
        }}
        runs={[RUN]}
        dataset={DATASET}
      />
    )
    expect(screen.getByText('Mean groundedness')).toBeInTheDocument()
    expect(screen.getByText('0.91')).toBeInTheDocument()
    expect(screen.getByText('over 0 items')).toBeInTheDocument()
  })
})

describe('EvalResults progressive disclosure', () => {
  it('keeps the detail tables closed until they are asked for', () => {
    render(<EvalResults run={RUN} runs={[RUN]} dataset={DATASET} />)
    for (const details of document.querySelectorAll('details')) {
      expect(details.open).toBe(false)
    }
  })

  it('renders recall and precision across every k once opened', async () => {
    const user = userEvent.setup()
    render(<EvalResults run={RUN} runs={[RUN]} dataset={DATASET} />)

    await open(user, 'Scores at k')
    const table = screen.getByRole('table', { name: /scores at each cutoff/i })
    expect(within(table).getByText('Recall@k')).toBeInTheDocument()
    expect(within(table).getByText('Precision@k')).toBeInTheDocument()
    expect(within(table).getByText('75%')).toBeInTheDocument()
  })

  it('lists the failures first in the per-item drill-down', async () => {
    const user = userEvent.setup()
    render(<EvalResults run={RUN} runs={[RUN]} dataset={DATASET} />)

    await open(user, 'Per-item results')
    const rows = within(screen.getByRole('table', { name: /per-item/i })).getAllByRole('row')
    expect(rows[1]).toHaveTextContent('never found')
    expect(rows[1]).toHaveTextContent('Ranked out of the context')
    expect(rows[2]).toHaveTextContent('found first')
  })

  it('never hides a stale-label warning behind a disclosure', () => {
    render(
      <EvalResults
        run={{
          ...RUN,
          label_validation: {
            checked: true,
            stale_label_count: 3,
            stale_item_count: 2,
            stale_ids: ['c9'],
          },
        }}
        runs={[RUN]}
        dataset={DATASET}
      />
    )
    const warning = screen.getByText('Benchmark labels no longer exist')
    expect(warning.closest('details')).toBeNull()
    expect(screen.getByText(/not retrieval misses/i)).toBeInTheDocument()
  })

  it('never hides a failed run behind a disclosure', () => {
    render(
      <EvalResults
        run={{ ...RUN, status: 'failed', error: 'Vector store unavailable' }}
        runs={[RUN]}
        dataset={DATASET}
      />
    )
    const error = screen.getByText('Vector store unavailable')
    expect(error.closest('details')).toBeNull()
  })

  it('warns when the two most recent runs used different settings', async () => {
    const user = userEvent.setup()
    const previous = {
      ...RUN,
      run_id: 'r-1',
      config_snapshot: { ...SNAPSHOT, top_k_documents: 10, reranker_active: true },
    }
    render(<EvalResults run={RUN} runs={[RUN, previous]} dataset={DATASET} />)

    expect(screen.getByText('Configuration changed between runs')).toBeInTheDocument()
    await open(user, 'Configuration changed between runs')
    expect(screen.getByText('Top-k documents')).toBeInTheDocument()
    // Booleans read as words, not as true/false.
    expect(screen.getByText('Off')).toBeInTheDocument()
    expect(screen.getByText(/Affects: Embedding model/)).toBeInTheDocument()
  })

  it('stays silent about configuration when the two runs agree', () => {
    render(<EvalResults run={RUN} runs={[RUN, { ...RUN, run_id: 'r-1' }]} dataset={DATASET} />)
    expect(screen.queryByText('Configuration changed between runs')).not.toBeInTheDocument()
  })
})

describe('EvalResults dataset provenance', () => {
  it('names the version and fingerprint of the labels the run scored', () => {
    render(<EvalResults run={RUN} runs={[RUN]} dataset={DATASET} />)
    expect(screen.getByText(/version 2, fingerprint/)).toBeInTheDocument()
    expect(screen.getByText('20b2ea7875df')).toHaveAttribute('title', SHA)
  })

  it('warns when the dataset has been edited since the run', () => {
    render(
      <EvalResults run={RUN} runs={[RUN]} dataset={{ ...DATASET, dataset_sha256: 'other' }} />
    )
    expect(screen.getByText(/has been edited since this run/i)).toBeInTheDocument()
  })

  it('says a pre-versioning run recorded nothing rather than borrowing the current labels', () => {
    render(
      <EvalResults
        run={{ ...RUN, dataset_sha256: null, dataset_version: null }}
        runs={[RUN]}
        dataset={DATASET}
      />
    )
    expect(screen.getByText(/predates dataset versioning/i)).toBeInTheDocument()
  })
})

describe('DatasetProvenance', () => {
  it('compares against the dataset only when the dataset carries a fingerprint', () => {
    render(<DatasetProvenance run={RUN} dataset={{ dataset_id: 'd-1' }} />)
    expect(screen.queryByText(/has been edited since this run/i)).not.toBeInTheDocument()
  })
})

describe('LabelValidation', () => {
  it('renders nothing at all without a validation record', () => {
    const { container } = render(<LabelValidation validation={undefined} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('warns when a run scored without its labels being verified', () => {
    render(<LabelValidation validation={{ checked: false, reason: 'unavailable' }} />)
    expect(screen.getByText('Labels were not verified')).toBeInTheDocument()
    expect(screen.getByText(/could not be reached to verify them/i)).toBeInTheDocument()
  })

  it('keeps a suppressed label apart from a deleted one', () => {
    render(
      <LabelValidation
        validation={{
          checked: true,
          stale_label_count: 1,
          stale_item_count: 1,
          stale_ids: ['gone'],
          unretrievable_label_count: 2,
          unretrievable_ids: ['barred'],
        }}
      />
    )
    expect(screen.getByText(/Missing ids: gone/)).toBeInTheDocument()
    expect(screen.getByText(/Unreachable ids: barred/)).toBeInTheDocument()
    expect(screen.getAllByText(/excluded from retrieval/i).length).toBeGreaterThan(0)
  })

  it('says nothing loud about a clean check', () => {
    const { container } = render(<LabelValidation validation={{ checked: true }} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('FailureAttribution', () => {
  it('lists only the stages that actually lost items', () => {
    render(
      <FailureAttribution
        attribution={{
          items_attributed: 10,
          items_without_failure: 7,
          items_unclassified: 1,
          counts: { ranking: 2, retrieval: 0, index: 0 },
          rates: { ranking: 0.2 },
        }}
      />
    )
    expect(screen.getByText('Ranked out of the context')).toBeInTheDocument()
    expect(screen.queryByText('Never a candidate')).not.toBeInTheDocument()
    expect(screen.getByText('20%')).toBeInTheDocument()
  })

  it('renders nothing when no item could be attributed', () => {
    const { container } = render(<FailureAttribution attribution={{ items_attributed: 0 }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('says so rather than showing an empty table when nothing failed', () => {
    render(
      <FailureAttribution
        attribution={{ items_attributed: 5, items_without_failure: 5, counts: {} }}
      />
    )
    expect(screen.getByText(/nothing to attribute/i)).toBeInTheDocument()
  })
})

describe('diffSnapshots', () => {
  it('reports only the keys that differ', () => {
    expect(diffSnapshots({ a: 1, b: 2 }, { a: 1, b: 3 })).toEqual([
      { key: 'b', current: 2, previous: 3 },
    ])
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

describe('failureLabel', () => {
  it('leaves a row from before attribution existed blank rather than guessing', () => {
    expect(failureLabel({ item_id: 'i' })).toBe('—')
  })

  it('leaves an item that did not fail blank', () => {
    expect(failureLabel({ failure_attribution: { category: 'none' } })).toBe('—')
  })
})
