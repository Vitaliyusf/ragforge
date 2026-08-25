/**
 * Tests for the quality panel.
 *
 * Two things this panel must never do, and both are asserted below: blend the
 * claim-level hallucination rate with the older groundedness proxy into one
 * number, and print a citation figure without the denominator it was taken
 * over. An absent measurement renders as `—`, never as `NaN%` or `0%`.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import QualityPanel from './QualityPanel'

/** A window entirely after the phase-6 deploy: every turn carries a verdict. */
const JUDGED = {
  turns: 10,
  scored_turns: 10,
  mean_groundedness: 0.86,
  hallucination_rate: 0.2,
  hallucination_severe_rate: 0.1,
  hallucination_verdict_turns: 10,
  turns_without_verdict: 0,
  hallucination_verdict_mix: [
    { verdict: 'none', count: 8 },
    { verdict: 'minor', count: 1 },
    { verdict: 'severe', count: 1 },
  ],
  mean_unsupported_claims: 0.4,
  unsupported_claim_turns: 10,
  hallucination_rate_proxy_groundedness: 0.3,
  hallucination_groundedness_threshold: 0.6,
  mean_citation_precision: 0.9,
  citation_precision_turns: 8,
  citation_precision_excluded: 2,
  mean_citation_recall: 0.75,
  citation_recall_turns: 9,
  citation_recall_excluded: 1,
  citation_f1: 0.82,
  mean_citation_count: 1.6,
  answers_with_citations: 8,
  revision_rate: 0.1,
  guardrail_block_rate: 0.0,
  groundedness_histogram: [{ bucket: '0.8-1.01', count: 8 }],
  completeness_histogram: [],
  safety_histogram: [],
  confidence_mix: [{ level: 'high', count: 8 }],
  worst_turns: [],
}

/** A window straddling the deploy: two judged turns, eight older ones. */
const MIXED = {
  ...JUDGED,
  hallucination_rate: 0.5,
  hallucination_verdict_turns: 2,
  turns_without_verdict: 8,
  hallucination_verdict_mix: [
    { verdict: 'none', count: 1 },
    { verdict: 'minor', count: 1 },
  ],
}

describe('QualityPanel', () => {
  it('leads with the claim-level hallucination rate over its own denominator', () => {
    render(<QualityPanel data={JUDGED} />)

    expect(screen.getAllByText('Hallucination rate').length).toBeGreaterThan(0)
    expect(screen.getAllByText('20%').length).toBeGreaterThan(0)
    expect(screen.getByText(/10 judged, 0 without a verdict/)).toBeInTheDocument()
  })

  it('hides the proxy entirely when every turn in the window was judged', () => {
    render(<QualityPanel data={JUDGED} />)

    expect(screen.queryByText('Hallucination rate (proxy)')).not.toBeInTheDocument()
  })

  it('shows both measures with an explanatory note on a mixed window', () => {
    render(<QualityPanel data={MIXED} />)

    // Both present, each over its own population, never averaged together.
    expect(screen.getByText('Hallucination rate (proxy)')).toBeInTheDocument()
    expect(screen.getAllByText('50%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('30%').length).toBeGreaterThan(0)
    expect(screen.getByText(/predate claim-level judging/)).toBeInTheDocument()
    expect(screen.getByText(/2 judged, 8 without a verdict/)).toBeInTheDocument()
  })

  it('omits the mixed-window note when there is nothing to disambiguate', () => {
    render(<QualityPanel data={JUDGED} />)

    expect(screen.queryByText(/predate claim-level judging/)).not.toBeInTheDocument()
  })

  it('falls back to the proxy when no turn in the window carries a verdict', () => {
    render(
      <QualityPanel
        data={{ ...JUDGED, hallucination_verdict_turns: 0, hallucination_rate: null }}
      />
    )

    expect(screen.getByText('Hallucination rate (proxy)')).toBeInTheDocument()
  })

  it('shows every citation figure with the answers it was measured over', () => {
    render(<QualityPanel data={JUDGED} />)

    expect(screen.getByText('Citation precision')).toBeInTheDocument()
    expect(screen.getByText(/over 8 answers · 2 had no citations/)).toBeInTheDocument()
    expect(screen.getByText('Citation recall')).toBeInTheDocument()
    expect(screen.getByText(/over 9 answers · 1 had no supportable claims/)).toBeInTheDocument()
    expect(screen.getByText('Citation F1')).toBeInTheDocument()
  })

  it('renders zero-denominator citation stats as em dashes, not NaN', () => {
    render(
      <QualityPanel
        data={{
          ...JUDGED,
          mean_citation_precision: null,
          citation_precision_turns: 0,
          citation_precision_excluded: 0,
          mean_citation_recall: null,
          citation_recall_turns: 0,
          citation_recall_excluded: 0,
          citation_f1: null,
          mean_citation_count: null,
        }}
      />
    )

    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('reports unsupported claims per answer as a decimal, not a percentage', () => {
    render(<QualityPanel data={JUDGED} />)

    expect(screen.getByText('Unsupported claims per answer')).toBeInTheDocument()
    expect(screen.getByText('0.4')).toBeInTheDocument()
  })

  it('extends the worst-turns table with claim counts and verdicts', () => {
    render(
      <QualityPanel
        data={{
          ...JUDGED,
          worst_turns: [
            {
              turn_id: 'turn-1',
              conversation_id: 'conv-1',
              ts: '2026-08-20T10:00:00Z',
              groundedness: 0.1,
              completeness: 0.4,
              safety: 1,
              confidence: 'low',
              unsupported_claim_count: 3,
              hallucination_verdict: 'severe',
            },
          ],
        }}
      />
    )

    const table = within(screen.getByRole('table'))
    expect(table.getByText('Unsupported claims')).toBeInTheDocument()
    expect(table.getByText('3')).toBeInTheDocument()
    expect(table.getByText('Severe')).toBeInTheDocument()
  })

  it('renders a pre-phase-6 worst turn without inventing a verdict', () => {
    render(
      <QualityPanel
        data={{
          ...JUDGED,
          worst_turns: [
            {
              turn_id: 'turn-old',
              ts: '2026-08-20T10:00:00Z',
              groundedness: 0.2,
              completeness: 0.3,
              safety: 1,
              confidence: 'low',
              unsupported_claim_count: null,
              hallucination_verdict: null,
            },
          ],
        }}
      />
    )

    // Nothing measured, so nothing claimed: em dashes, not "None" or "0".
    const table = within(screen.getByRole('table'))
    expect(table.queryByText('None')).not.toBeInTheDocument()
    expect(table.getAllByText('—').length).toBe(2)
  })
})
