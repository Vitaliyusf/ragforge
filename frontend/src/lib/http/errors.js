/** HTTP and runtime error normalization utilities */

export function createAppError(message, metadata = {}) {
  const error = new Error(message || 'An error occurred')
  error.name = metadata.name || 'AppError'
  error.status = metadata.status ?? null
  error.statusText = metadata.statusText ?? null
  error.type = metadata.type || 'app'
  error.code = metadata.code || null
  error.origin = metadata.origin || null
  error.retryable = Boolean(metadata.retryable)
  error.request_id = metadata.request_id || null
  error.trace_id = metadata.trace_id || null
  error.correlation_id = metadata.correlation_id || null
  error.details = metadata.details || null
  error.runtimeEvent = metadata.runtimeEvent || null
  error.runtimeHandled = Boolean(metadata.runtimeHandled)
  error.payload = metadata.payload || null
  return error
}

export function normalizeError(error) {
  if (error instanceof Error && error.type) {
    return error
  }

  if (error instanceof Response) {
    return createAppError(`HTTP ${error.status}: ${error.statusText}`, {
      status: error.status,
      statusText: error.statusText,
      type: 'http',
    })
  }

  if (error instanceof Error) {
    return createAppError(error.message || 'An error occurred', {
      status: error.status,
      statusText: error.statusText,
      type: error.type || 'error',
      code: error.code,
      origin: error.origin,
      retryable: error.retryable,
      request_id: error.request_id,
      trace_id: error.trace_id,
      correlation_id: error.correlation_id,
      details: error.details,
      runtimeEvent: error.runtimeEvent,
      runtimeHandled: error.runtimeHandled,
      payload: error.payload,
      name: error.name,
    })
  }

  if (typeof error === 'object' && error !== null) {
    return createAppError(error.message || error.error || 'An error occurred', {
      status: error.status,
      statusText: error.statusText,
      type: error.type || 'api',
      code: error.code || error.error_code,
      origin: error.origin,
      retryable: error.retryable,
      request_id: error.request_id,
      trace_id: error.trace_id,
      correlation_id: error.correlation_id,
      details: error.details,
      payload: error,
    })
  }

  return createAppError(String(error) || 'An error occurred', {
    type: 'unknown',
  })
}

export async function extractErrorPayload(response) {
  try {
    return await response.json()
  } catch {
    return null
  }
}

export async function extractErrorMessage(response) {
  const data = await extractErrorPayload(response)
  return data?.message || data?.error || `HTTP ${response.status}: ${response.statusText}`
}

export async function createHttpError(response) {
  const data = await extractErrorPayload(response)
  return createAppError(
    data?.message || data?.error || `HTTP ${response.status}: ${response.statusText}`,
    {
      status: response.status,
      statusText: response.statusText,
      type: 'http',
      code: data?.code || data?.error_code || null,
      origin: data?.origin || null,
      retryable: data?.retryable || false,
      request_id: data?.request_id || null,
      trace_id: data?.trace_id || null,
      correlation_id: data?.correlation_id || null,
      details: data?.details || null,
      payload: data || null,
    }
  )
}
