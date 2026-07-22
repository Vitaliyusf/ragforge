/** Centralized HTTP client */
import { config } from '@/lib/config'
import { normalizeError, createHttpError } from '@/lib/http/errors'
import { logger } from '@/lib/logger'

const DEFAULT_TIMEOUT = 30000 // 30 seconds
const UPLOAD_TIMEOUT = 120000 // 120 seconds — uploads go through GridFS + Kafka round-trip
const MAX_RETRIES = 3
const RETRY_BASE_DELAY = 500 // 500ms

function isRetryable(error, status) {
  if (error?.type === 'timeout') return true
  if (error?.name === 'TypeError') return true // network failure
  if (status >= 500 && status !== 501) return true
  if (status === 429) return true
  return false
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function readCookie(name) {
  if (typeof document === 'undefined') return null
  const prefix = `${encodeURIComponent(name)}=`
  const entry = document.cookie.split('; ').find((item) => item.startsWith(prefix))
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null
}

function securityHeaders(method, headers = {}) {
  const normalizedMethod = String(method || 'GET').toUpperCase()
  const csrfToken = readCookie(config.csrfCookieName)
  return {
    ...headers,
    ...(csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(normalizedMethod)
      ? { 'X-CSRF-Token': csrfToken }
      : {}),
  }
}

async function parseJsonResponse(response) {
  if (response.status === 204) return null
  try {
    return await response.json()
  } catch (_) {
    return null
  }
}

/**
 * HTTP client with base URL, headers, JSON parsing, and timeout
 * @param {string} url - Endpoint URL (relative to base URL)
 * @param {RequestInit} options - Fetch options
 * @returns {Promise<Response>} Fetch response
 */
export async function httpClient(url, options = {}) {
  const {
    timeout = DEFAULT_TIMEOUT,
    headers = {},
    retries = MAX_RETRIES,
    ...fetchOptions
  } = options

  const fullUrl = url.startsWith('http') ? url : `${config.apiBaseUrl}${url}`
  const method = String(fetchOptions.method || 'GET').toUpperCase()

  const defaultHeaders = {
    'Content-Type': 'application/json',
    ...securityHeaders(method, headers)
  }

  let lastError = null

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    try {
      const response = await fetch(fullUrl, {
        ...fetchOptions,
        credentials: 'include',
        headers: defaultHeaders,
        signal: controller.signal
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        const httpError = await createHttpError(response)
        logger.error('HTTP request failed', {
          url: fullUrl,
          method: fetchOptions.method || 'GET',
          attempt,
          status: httpError.status,
          code: httpError.code,
          request_id: httpError.request_id,
          trace_id: httpError.trace_id,
        })
        if (attempt < retries && ['GET', 'HEAD'].includes(method) && isRetryable(null, response.status)) {
          lastError = httpError
          const delay = RETRY_BASE_DELAY * Math.pow(2, attempt) * (0.5 + Math.random() * 0.5)
          await sleep(delay)
          continue
        }
        throw httpError
      }

      return response
    } catch (error) {
      clearTimeout(timeoutId)

      if (error.name === 'AbortError') {
        lastError = normalizeError({
          message: `Request timeout after ${timeout}ms`,
          type: 'timeout',
          retryable: true,
        })
      } else {
        lastError = normalizeError(error)
      }

      logger.error('HTTP request exception', {
        url: fullUrl,
        method: fetchOptions.method || 'GET',
        attempt,
        message: lastError.message,
        status: lastError.status,
        code: lastError.code,
        request_id: lastError.request_id,
        trace_id: lastError.trace_id,
      })

      if (attempt < retries && ['GET', 'HEAD'].includes(method) && isRetryable(lastError, lastError?.status)) {
        const delay = RETRY_BASE_DELAY * Math.pow(2, attempt) * (0.5 + Math.random() * 0.5)
        await sleep(delay)
        continue
      }

      throw lastError
    }
  }

  throw lastError
}

/**
 * GET request
 * @param {string} url - Endpoint URL
 * @param {RequestInit} options - Fetch options
 * @returns {Promise<Object>} JSON response
 */
export async function get(url, options = {}) {
  const response = await httpClient(url, {
    ...options,
    method: 'GET'
  })
  return await parseJsonResponse(response)
}

/**
 * POST request
 * @param {string} url - Endpoint URL
 * @param {Object} data - Request body
 * @param {RequestInit} options - Fetch options
 * @returns {Promise<Object>} JSON response
 */
export async function post(url, data, options = {}) {
  const response = await httpClient(url, {
    ...options,
    method: 'POST',
    body: JSON.stringify(data)
  })
  return await parseJsonResponse(response)
}

/**
 * PUT request
 * @param {string} url - Endpoint URL
 * @param {Object} data - Request body
 * @param {RequestInit} options - Fetch options
 * @returns {Promise<Object>} JSON response
 */
export async function put(url, data, options = {}) {
  const response = await httpClient(url, {
    ...options,
    method: 'PUT',
    body: JSON.stringify(data)
  })
  return await parseJsonResponse(response)
}

export async function patch(url, data, options = {}) {
  const response = await httpClient(url, {
    ...options,
    method: 'PATCH',
    body: JSON.stringify(data)
  })
  return await parseJsonResponse(response)
}

/**
 * DELETE request
 * @param {string} url - Endpoint URL
 * @param {RequestInit} options - Fetch options
 * @returns {Promise<Object>} JSON response
 */
export async function del(url, options = {}) {
  const response = await httpClient(url, {
    ...options,
    method: 'DELETE'
  })
  return await parseJsonResponse(response)
}

/**
 * Upload file (multipart/form-data)
 * @param {string} url - Endpoint URL
 * @param {FormData} formData - Form data
 * @param {RequestInit} options - Fetch options
 * @returns {Promise<Object>} JSON response
 */
export async function upload(url, formData, options = {}) {
  const fullUrl = url.startsWith('http') ? url : `${config.apiBaseUrl}${url}`
  const timeout = options.timeout || UPLOAD_TIMEOUT
  const retries = 0

  let lastError = null

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    try {
      const response = await fetch(fullUrl, {
        ...options,
        method: 'POST',
        body: formData,
        credentials: 'include',
        signal: controller.signal,
        headers: {
          // Don't set Content-Type for FormData, browser will set it with boundary
          ...securityHeaders('POST', options.headers || {})
        }
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        const httpError = await createHttpError(response)
        if (attempt < retries && isRetryable(null, response.status)) {
          lastError = httpError
          const delay = RETRY_BASE_DELAY * Math.pow(2, attempt) * (0.5 + Math.random() * 0.5)
          await sleep(delay)
          continue
        }
        throw httpError
      }

      return await parseJsonResponse(response)
    } catch (error) {
      clearTimeout(timeoutId)

      if (error.name === 'AbortError') {
        lastError = normalizeError({
          message: `Upload timeout after ${timeout}ms`,
          type: 'timeout',
          retryable: true,
        })
      } else {
        lastError = normalizeError(error)
      }

      logger.error('Upload request failed', {
        url: fullUrl,
        attempt,
        message: lastError.message,
        status: lastError.status,
        code: lastError.code,
        request_id: lastError.request_id,
        trace_id: lastError.trace_id,
      })

      if (attempt < retries && isRetryable(lastError, lastError?.status)) {
        const delay = RETRY_BASE_DELAY * Math.pow(2, attempt) * (0.5 + Math.random() * 0.5)
        await sleep(delay)
        continue
      }

      throw lastError
    }
  }

  throw lastError
}
