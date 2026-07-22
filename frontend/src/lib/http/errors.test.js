import { describe, expect, it } from 'vitest'

import { createAppError, createHttpError, normalizeError } from './errors'

describe('http error normalization', () => {
  it('preserves structured gateway error fields', async () => {
    const response = new Response(
      JSON.stringify({
        error: 'not_found',
        message: 'missing',
        code: 'NOT_FOUND',
        origin: { service: 'gateway', location: 'gateway:http_exception_handler' },
        request_id: 'req-1',
        trace_id: 'trace-1',
        correlation_id: 'corr-1',
        retryable: false,
        details: { field: 'id' },
      }),
      {
        status: 404,
        statusText: 'Not Found',
        headers: { 'Content-Type': 'application/json' },
      }
    )

    const error = await createHttpError(response)

    expect(error.message).toBe('missing')
    expect(error.code).toBe('NOT_FOUND')
    expect(error.origin).toEqual({ service: 'gateway', location: 'gateway:http_exception_handler' })
    expect(error.request_id).toBe('req-1')
    expect(error.trace_id).toBe('trace-1')
    expect(error.correlation_id).toBe('corr-1')
    expect(error.details).toEqual({ field: 'id' })
  })

  it('normalizes plain objects into app errors', () => {
    const error = normalizeError({
      message: 'Request timeout',
      type: 'timeout',
      retryable: true,
      code: 'TIMEOUT',
    })

    expect(error).toBeInstanceOf(Error)
    expect(error.retryable).toBe(true)
    expect(error.code).toBe('TIMEOUT')
  })

  it('keeps already normalized app errors intact', () => {
    const original = createAppError('Already normalized', { code: 'READY', type: 'http' })
    const normalized = normalizeError(original)

    expect(normalized).toBe(original)
  })
})
