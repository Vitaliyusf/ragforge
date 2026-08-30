/**
 * OBS-UX-01 — a log line read as an event.
 *
 * The point of parsing is the correlation ids: they are what makes a line
 * actionable. Everything else here guards against the parser inventing
 * structure a plain line never had.
 */
import { describe, expect, it } from 'vitest'

import { parseLogEvent } from './logs'

const STRUCTURED = JSON.stringify({
  timestamp: '2026-01-01T12:00:00Z',
  service: 'rag',
  location: 'retrieval.py:88',
  message: 'Retrieval returned no candidates',
  severity: 'ERROR',
  trace_id: 'trace-9f2c',
  data: { request_id: 'req-1', candidates: 0 },
})

describe('parseLogEvent', () => {
  it('lifts correlation ids from both the entry and its data payload', () => {
    const event = parseLogEvent(STRUCTURED)

    expect(event.identifiers).toEqual([
      { field: 'trace_id', label: 'Trace', kindLabel: 'trace', value: 'trace-9f2c' },
      { field: 'request_id', label: 'Request', kindLabel: 'request', value: 'req-1' },
    ])
  })

  it('keeps the rest of the payload as secondary detail without repeating the ids', () => {
    const event = parseLogEvent(STRUCTURED)

    expect(event.details).toEqual({ candidates: 0 })
    expect(event.message).toBe('Retrieval returned no candidates')
    expect(event.location).toBe('retrieval.py:88')
    expect(event.severity).toBe('error')
  })

  it('offers no detail block when the payload was nothing but ids', () => {
    const event = parseLogEvent(JSON.stringify({ message: 'ok', data: { trace_id: 't-1' } }))

    expect(event.details).toBeNull()
    expect(event.identifiers).toHaveLength(1)
  })

  it('invents no fields for a line that is not structured', () => {
    const event = parseLogEvent('plain text failure')

    expect(event.structured).toBe(false)
    expect(event.message).toBe('plain text failure')
    expect(event.timestamp).toBeNull()
    expect(event.identifiers).toEqual([])
  })

  it('treats a bare JSON array as unstructured rather than as an entry', () => {
    const event = parseLogEvent('[1, 2, 3]')
    expect(event.structured).toBe(false)
    expect(event.message).toBe('[1, 2, 3]')
  })
})
