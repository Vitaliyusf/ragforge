/**
 * Tests for the retrieval panel.
 *
 * The panel takes its data as props, so these render it directly rather than
 * mocking the hook — `MetricsTab.test.jsx` already covers the hook wiring.
 *
 * The recurring assertion is that an absent measurement renders as `—` and
 * never as `NaN%` or `0%`: a confident zero over no data is the specific wrong
 * outcome this panel has to avoid.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import RetrievalPanel from './RetrievalPanel'

const DATA = {
  turns: 10,
  hit_rate: 0.75,
  empty_retrieval_rate: 0.25,
  mean_chunk_count: 4.2,
  mean_top_score: 0.82,
  mean_score_gap: 0.42,
  score_gap_turns: 6,
  reranker_changed_top1_rate: 0.4,
  reranker_evaluated_turns: 8,
  reranker_p95_seconds: 0.08,
  retrieval_filtered_rate: 0.1,
  retrieval_filtered_by_reason: { review_removed: 0.5 },
  vector_search_p95_seconds: { documents: 0.045 },
  vector_search_rate: { documents: 3.2 },
  top_score_histogram: [{ bucket: '0.8-1.01', count: 7 }],
  chunks_per_query: [{ bucket: '3-5', count: 6 }],
  score_gap_histogram: [{ bucket: '0.2-0.4', count: 4 }],
  reranker_top_score_histogram: [{ bucket: '5', count: 3 }],
}

describe('RetrievalPanel', () => {
  it('renders the KPI strip from the per-turn facts', () => {
    render(<RetrievalPanel data={DATA} />)

    expect(screen.getByText('Retrieval hit rate')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
    expect(screen.getByText('Empty retrievals')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
    expect(screen.getByText('Chunks per query')).toBeInTheDocument()
    expect(screen.getByText('4.2')).toBeInTheDocument()
    // Appears twice: the strip's slowest-collection figure and the table row.
    expect(screen.getAllByText('45 ms').length).toBe(2)
  })

  it('shows the reranker lift and its latency together', () => {
    // The brief's point: lift alone cannot answer "is it earning its latency".
    render(<RetrievalPanel data={DATA} />)

    expect(screen.getByText('Reranker lift')).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()
    expect(screen.getByText('Reranker p95')).toBeInTheDocument()
    expect(screen.getByText('80 ms')).toBeInTheDocument()
    expect(screen.getByText(/of 8 reranked turns/)).toBeInTheDocument()
  })

  it('shows the score-gap denominator so a small sample cannot be misread', () => {
    render(<RetrievalPanel data={DATA} />)

    expect(screen.getByText(/6 of 10 turns returned enough chunks/)).toBeInTheDocument()
    expect(screen.getByText('0.42')).toBeInTheDocument()
  })

  it('renders an empty state when no turns reached retrieval', () => {
    render(<RetrievalPanel data={{ turns: 0 }} />)

    expect(screen.getByText('No retrieval activity')).toBeInTheDocument()
    // The specific wrong outcome: a page of zeroes and NaN% for an idle window.
    expect(document.body.textContent).not.toMatch(/NaN/)
    expect(screen.queryByText('Reranker lift')).not.toBeInTheDocument()
  })

  it('never renders NaN for a window with partial data', () => {
    // Turns were recorded, but nothing else was measured.
    render(<RetrievalPanel data={{ turns: 3 }} />)

    expect(document.body.textContent).not.toMatch(/NaN/)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('degrades only the Prometheus widgets when the store is down', () => {
    render(<RetrievalPanel data={DATA} promAvailable={false} />)

    expect(screen.getAllByText(/Metrics store unavailable/i).length).toBeGreaterThan(0)
    // MongoDB-backed figures are untouched by a Prometheus outage...
    expect(screen.getByText('75%')).toBeInTheDocument()
    expect(screen.getByText('4.2')).toBeInTheDocument()
    // ...while the Prometheus-backed ones blank rather than showing a stale value.
    expect(screen.queryByText('80 ms')).not.toBeInTheDocument()
    expect(screen.queryByText('45 ms')).not.toBeInTheDocument()
  })

  it('renders an error state with a retry action', () => {
    const onRetry = vi.fn()
    render(<RetrievalPanel error="Gateway timeout" onRetry={onRetry} />)

    expect(screen.getByText('Could not load retrieval metrics')).toBeInTheDocument()
    expect(screen.getByText('Gateway timeout')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('gives every table a caption and every figure a label', () => {
    render(<RetrievalPanel data={DATA} />)

    for (const table of document.querySelectorAll('table')) {
      expect(table.querySelector('caption')?.textContent?.trim()).toBeTruthy()
    }
    for (const figure of document.querySelectorAll('svg[role="img"]')) {
      expect(figure.getAttribute('aria-label')).toBeTruthy()
    }
  })
})
