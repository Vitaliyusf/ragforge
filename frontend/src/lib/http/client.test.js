/**
 * Tests for the centralized HTTP client.
 * Tests: retries, timeouts, error handling, method helpers.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { httpClient, get, post, put, del } from './client'

// Mock config
vi.mock('@/lib/config', () => ({
  config: { apiBaseUrl: 'http://test-api:8000' },
}))

// Mock logger
vi.mock('@/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  },
}))

// Mock errors module
vi.mock('@/lib/http/errors', () => ({
  normalizeError: (err) => ({
    message: err.message || 'Unknown error',
    status: err.status || 0,
    code: err.code,
    type: err.type,
    retryable: err.retryable || false,
  }),
  createHttpError: async (response) => {
    let body = {}
    try { body = await response.clone().json() } catch {}
    return {
      message: body.message || `HTTP ${response.status}`,
      status: response.status,
      code: body.error_code || 'UNKNOWN',
    }
  },
}))

describe('httpClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('makes GET request with correct URL', async () => {
    const mockResponse = new Response(JSON.stringify({ ok: true }), { status: 200 })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    const response = await httpClient('/v1/health', { method: 'GET', retries: 0 })
    expect(response.ok).toBe(true)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://test-api:8000/v1/health',
      expect.objectContaining({ method: 'GET' })
    )
  })

  it('passes absolute URLs through unchanged', async () => {
    const mockResponse = new Response('{}', { status: 200 })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    await httpClient('http://other:9000/foo', { retries: 0 })
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://other:9000/foo',
      expect.anything()
    )
  })

  it('throws on non-2xx without retries', async () => {
    const mockResponse = new Response(JSON.stringify({ message: 'Not Found' }), { status: 404 })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    await expect(httpClient('/v1/missing', { retries: 0 })).rejects.toMatchObject({
      status: 404,
    })
  })

  it('retries on 500 errors', async () => {
    const error500 = new Response(JSON.stringify({ message: 'Server Error' }), { status: 500 })
    const success = new Response(JSON.stringify({ ok: true }), { status: 200 })

    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(error500)
      .mockResolvedValueOnce(success)

    const response = await httpClient('/v1/test', { retries: 1 })
    expect(response.ok).toBe(true)
    expect(globalThis.fetch).toHaveBeenCalledTimes(2)
  })

  it('does not retry on 400 errors', async () => {
    const error400 = new Response(JSON.stringify({ message: 'Bad Request' }), { status: 400 })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(error400)

    await expect(httpClient('/v1/test', { retries: 3 })).rejects.toMatchObject({
      status: 400,
    })
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })
})

describe('get', () => {
  it('returns parsed JSON', async () => {
    const mockResponse = new Response(JSON.stringify({ data: 'hello' }), { status: 200 })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    const result = await get('/v1/test', { retries: 0 })
    expect(result).toEqual({ data: 'hello' })
  })
})

describe('post', () => {
  it('sends JSON body', async () => {
    const mockResponse = new Response(JSON.stringify({ created: true }), { status: 200 })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    const result = await post('/v1/test', { key: 'value' }, { retries: 0 })
    expect(result).toEqual({ created: true })

    const [, opts] = globalThis.fetch.mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(opts.body).toBe(JSON.stringify({ key: 'value' }))
  })
})

describe('put', () => {
  it('sends PUT request', async () => {
    const mockResponse = new Response(JSON.stringify({ updated: true }), { status: 200 })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    await put('/v1/test', { data: 1 }, { retries: 0 })
    const [, opts] = globalThis.fetch.mock.calls[0]
    expect(opts.method).toBe('PUT')
  })
})

describe('del', () => {
  it('sends DELETE request', async () => {
    const mockResponse = new Response(JSON.stringify({ deleted: true }), { status: 200 })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse)

    await del('/v1/test', { retries: 0 })
    const [, opts] = globalThis.fetch.mock.calls[0]
    expect(opts.method).toBe('DELETE')
  })
})
