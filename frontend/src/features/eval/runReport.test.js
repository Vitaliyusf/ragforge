/**
 * Tests for the run report's data model.
 *
 * These pin the claims the report is allowed to make: a stage that never
 * ran is not a failure, an unmeasured figure is a dash rather than a
 * confident zero, a delta on a metric with no defined direction is not
 * coloured, and two runs with different provenance are not comparable
 * however close their numbers are.
 */
import { describe, expect, it } from 'vitest'

import {
  buildComparison,
  benchmarkReport,
  deltaTone,
  diffSnapshots,
  evaluationReport,
  executionFlow,
  explainFailure,
  failureLabel,
  filterItems,
  isFailedItem,
  itemBand,
  kpiSummary,
  latencySummary,
  validationStage,
} from './runReport'

const MANIFEST = {
  dataset: { phases: ['retrieval_base'] },
  chunking: { size: 800 },
  vector_store: { collection: 'c' },
  embedding: { model: 'e5' },
  llm: { model: 'qwen' },
  retrieval: { top_k: 6 },
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
    dataset_version: 2,
    dataset_sha256: 'sha',
    dataset_name: 'golden_smoke_30',
    manifest: MANIFEST,
    progress: { items_per_phase: 30, completed_phases: 2, executable_phases: 2 },
    phases: [
      {
        name: 'retrieval_base',
        status: 'completed',
        results: { mrr: 0.8, mean_latency_ms: 120, items_evaluated: 30, items_failed: 0 },
      },
      {
        name: 'end_to_end_regular',
        status: 'completed',
        results: { mrr: 0.6, mean_latency_ms: 900, items_evaluated: 30, items_failed: 2 },
      },
    ],
    ...overrides,
  }
}

describe('validationStage', () => {
  it('reports an unverified check as unknown rather than as a pass', () => {
    expect(validationStage({ checked: false }).status).toBe('unknown')
    expect(validationStage(null).status).toBe('unknown')
  })

  it('reports stale labels as partial, with the count in words', () => {
    const stage = validationStage({ checked: true, stale_label_count: 3 })
    expect(stage.status).toBe('partial')
    expect(stage.note).toMatch(/3 labels are no longer in the index/)
  })
})

describe('executionFlow', () => {
  it('names the stage that stopped a downstream one, and never marks it failed', () => {
    const flow = executionFlow([
      { key: 'a', label: 'Retrieval', status: 'failed' },
      { key: 'b', label: 'End-to-end', status: 'queued' },
    ])
    expect(flow[1].status).toBe('skipped')
    expect(flow[1].blockedBy).toBe('Retrieval')
    expect(flow[1].note).toMatch(/Not run: Retrieval failed first/)
  })

  it('leaves an unsupported stage alone: it did not fail and it was not skipped', () => {
    const flow = executionFlow([
      { key: 'a', label: 'Retrieval', status: 'completed' },
      { key: 'b', label: 'Extended', status: 'unsupported', note: 'No graph on this build' },
    ])
    expect(flow[1].status).toBe('unsupported')
    expect(flow[1].blockedBy).toBeUndefined()
  })

  it('does not blame a later stage on a stage that merely finished partially', () => {
    const flow = executionFlow([
      { key: 'a', label: 'Retrieval', status: 'partial' },
      { key: 'b', label: 'End-to-end', status: 'queued' },
    ])
    expect(flow[1].status).toBe('queued')
  })
})

describe('latencySummary', () => {
  it('takes percentiles from the values a run actually recorded', () => {
    const rows = [{ latency_ms: 10 }, { latency_ms: 20 }, { latency_ms: 100 }]
    expect(latencySummary(rows)).toEqual({ p50: 20, p95: 100, sample: 3 })
  })

  it('reports nulls rather than zeros when no row carries a latency', () => {
    expect(latencySummary([{ latency_ms: null }])).toEqual({ p50: null, p95: null, sample: 0 })
  })
})

describe('kpiSummary', () => {
  it('states the sample every mean was taken over', () => {
    const cards = kpiSummary({
      results: { mrr: 0.75, items_evaluated: 20, items_skipped: 1, items_unscorable: 0 },
      items: [{ latency_ms: 5 }, { latency_ms: 9 }],
    })
    const mrr = cards.find((card) => card.key === 'mrr')
    expect(mrr.value).toBe('0.75')
    expect(mrr.subLabel).toMatch(/over 20 scored items/)
    const latency = cards.find((card) => card.key === 'latency')
    expect(latency.subLabel).toMatch(/over 2 queries/)
  })

  it('renders an unmeasured figure as a dash, never as a zero', () => {
    const cards = kpiSummary({ results: { items_evaluated: 3 }, items: [] })
    expect(cards.find((card) => card.key === 'mrr').value).toBe('—')
    expect(cards.find((card) => card.key === 'recall').value).toBe('—')
    expect(cards.find((card) => card.key === 'latency').subLabel).toMatch(/no per-item latencies/)
  })

  it('reports answer quality only for a run that produced answers', () => {
    expect(kpiSummary({ results: {}, items: [] }).some((card) => card.key === 'groundedness')).toBe(
      false
    )
    const withQuality = kpiSummary({
      results: { answer_quality: { groundedness: { mean: 0.9 }, items_judged: 18, items_unjudged: 2 } },
      items: [],
    })
    expect(withQuality.find((card) => card.key === 'groundedness').subLabel).toMatch(
      /18 judged, 2 unjudged/
    )
  })
})

describe('explainFailure', () => {
  const stages = executionFlow([
    { key: 'a', label: 'Retrieval', status: 'failed', note: 'Vector store unavailable' },
    { key: 'b', label: 'End-to-end', status: 'queued' },
  ])

  it('leads with what happened and keeps the raw error for the technical section', () => {
    const failure = explainFailure({ status: 'failed', error: 'Vector store unavailable', stages })
    expect(failure.happened).toMatch(/Retrieval failed/)
    expect(failure.impact).toMatch(/End-to-end never ran/)
    expect(failure.technical).toBe('Vector store unavailable')
    expect(failure.title).not.toContain('Vector store')
  })

  it('offers a cause only when the error text supports one', () => {
    expect(explainFailure({ status: 'failed', error: 'Vector store unavailable', stages }).cause).toMatch(
      /dependency/
    )
    expect(explainFailure({ status: 'failed', error: 'weird internal state', stages }).cause).toBeNull()
  })

  it('offers only the actions the page can actually perform', () => {
    expect(explainFailure({ status: 'failed', stages }).actions).toEqual([])
    expect(explainFailure({ status: 'failed', stages, retryable: true }).actions).toEqual(['retry'])
  })

  it('says nothing at all about a run that completed', () => {
    expect(explainFailure({ status: 'completed', stages })).toBeNull()
  })
})

describe('buildComparison', () => {
  it('refuses to call two runs comparable when their provenance differs', () => {
    const baseline = benchmark({
      benchmark_id: 'b-1',
      created_at: '2026-08-25T12:00:00Z',
      manifest: { ...MANIFEST, embedding: { model: 'other' } },
    })
    const comparison = buildComparison(benchmark(), [baseline])
    expect(comparison.comparable).toBe(false)
    expect(comparison.changes.map((change) => change.label)).toContain('Embedding')
    // Nothing is coloured on an invalid comparison, whatever the direction.
    expect(comparison.rows.every((row) => row.tone === null)).toBe(true)
  })

  it('colours a delta only for a metric whose direction is defined', () => {
    const baseline = benchmark({ benchmark_id: 'b-1', created_at: '2026-08-25T12:00:00Z' })
    const candidate = benchmark({
      phases: [
        {
          name: 'retrieval_base',
          status: 'completed',
          results: { mrr: 0.9, mean_latency_ms: 200 },
        },
      ],
    })
    const comparison = buildComparison(candidate, [baseline])
    expect(comparison.comparable).toBe(true)
    const mrr = comparison.rows.find((row) => row.metric === 'mrr')
    const latency = comparison.rows.find((row) => row.metric === 'latency')
    expect(mrr.tone).toBe('success')
    expect(mrr.deltaText).toBe('+0.10')
    // Slower is worse, and says so rather than borrowing "bigger is better".
    expect(latency.tone).toBe('danger')
  })

  it('says so when there is no earlier run at all', () => {
    expect(buildComparison(benchmark(), []).reason).toBe('no-baseline')
  })

  it('leaves a metric with no defined direction uncoloured', () => {
    expect(deltaTone('unknown_metric', 5)).toBeNull()
    expect(deltaTone('mrr', 0)).toBeNull()
  })
})

describe('item filtering', () => {
  const items = [
    { item_id: 'i-1', query: 'alpha', first_hit_rank: 1, outcome: 'success', reciprocal_rank: 1 },
    { item_id: 'i-2', query: 'beta', first_hit_rank: 4, outcome: 'success', reciprocal_rank: 0.25 },
    { item_id: 'i-3', query: 'gamma', first_hit_rank: null, outcome: 'success', reciprocal_rank: 0 },
    { item_id: 'i-4', query: 'delta', first_hit_rank: null, outcome: 'failed', error: 'boom' },
  ]

  it('puts the failures first', () => {
    expect(filterItems(items).map((row) => row.item_id)).toEqual(['i-4', 'i-3', 'i-2', 'i-1'])
  })

  it('keeps a retrieval miss out of the failure filter', () => {
    expect(isFailedItem(items[2])).toBe(false)
    expect(filterItems(items, { failuresOnly: true }).map((row) => row.item_id)).toEqual(['i-4'])
  })

  it('filters by score band', () => {
    expect(itemBand(items[0])).toBe('strong')
    expect(itemBand(items[1])).toBe('weak')
    expect(filterItems(items, { band: 'miss' }).map((row) => row.item_id)).toEqual(['i-4', 'i-3'])
  })

  it('searches the id and the question alike', () => {
    expect(filterItems(items, { search: 'i-2' }).map((row) => row.item_id)).toEqual(['i-2'])
    expect(filterItems(items, { search: 'GAM' }).map((row) => row.item_id)).toEqual(['i-3'])
  })
})

describe('diffSnapshots', () => {
  it('reports only the keys that differ', () => {
    expect(diffSnapshots({ a: 1, b: 2 }, { a: 1, b: 3 })).toEqual([
      { key: 'b', current: 2, previous: 3 },
    ])
  })

  it('never compares the unobserved list itself', () => {
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

describe('report subjects', () => {
  it('leads a benchmark with its profile and keeps the id as metadata', () => {
    const report = benchmarkReport(benchmark(), { name: 'golden_smoke_30' })
    expect(report.label).toBe('Full Quality')
    expect(report.id).toBe('b-2')
    expect(report.dataset.itemCount).toBe(30)
    // The last measured phase is what the run was for.
    expect(report.primary.key).toBe('end_to_end_regular')
    expect(report.stages[0].key).toBe('dataset_validation')
  })

  it('renders nothing for a subject that does not exist', () => {
    expect(benchmarkReport(null)).toBeNull()
    expect(evaluationReport(undefined)).toBeNull()
  })

  it('gives a single evaluation the per-item rows a benchmark does not carry', () => {
    const report = evaluationReport(
      {
        run_id: 'r-1',
        status: 'completed',
        mode: 'retrieval',
        started_at: '2026-08-26T12:00:00Z',
        results: { mrr: 0.5, items_evaluated: 2 },
        per_item: [{ item_id: 'i-1', query: 'q' }],
      },
      { name: 'golden_smoke_30' }
    )
    expect(report.kind).toBe('evaluation')
    expect(report.items).toHaveLength(1)
    expect(report.label).toBe('Retrieval only')
  })
})
