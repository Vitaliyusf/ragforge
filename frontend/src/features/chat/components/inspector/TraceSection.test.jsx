/**
 * OBS-UX-01 — the chat turn's correlation ids, made actionable.
 *
 * There is no trace store to open, so the honest offer is the log stream
 * filtered to the id the services actually logged this turn under. A
 * placeholder id gets no offer at all.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import TraceSection, { usableIdentifiers } from './TraceSection'

describe('usableIdentifiers', () => {
  it('drops the zero-UUID placeholder and the blanks', () => {
    expect(
      usableIdentifiers([
        ['Trace ID', 'trace-9f2c'],
        ['Request ID', '00000000-0000-0000-0000-000000000000'],
        ['Turn ID', null],
      ])
    ).toEqual([{ label: 'Trace ID', value: 'trace-9f2c' }])
  })
})

describe('TraceSection', () => {
  it('offers each real identifier as a jump into the log stream', () => {
    render(<TraceSection identifiers={[['Trace ID', 'trace-9f2c']]} />)

    const link = screen.getByRole('button', { name: /Find in Logs/i })
    expect(link).toHaveAttribute('title', expect.stringMatching(/trace id/i))
    // The offer must not read as a trace-store lookup, which does not exist.
    expect(link).toHaveAttribute('title', expect.stringMatching(/log lines/i))
  })

  it('offers nothing for a turn whose ids were never filled in', () => {
    render(
      <TraceSection
        identifiers={[['Trace ID', '00000000-0000-0000-0000-000000000000']]}
        traceEvents={[{ node: 'retrieve', latency: 120 }]}
      />
    )

    expect(screen.queryByRole('button', { name: /Find in Logs/i })).not.toBeInTheDocument()
  })
})
