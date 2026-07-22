/** Structured frontend logger wrapper */

const isDevelopment = process.env.NODE_ENV === 'development'

function normalizePayload(level, args) {
  const [message, context] = args
  return {
    timestamp: Date.now(),
    level,
    message: typeof message === 'string' ? message : 'Frontend log event',
    context:
      context && typeof context === 'object'
        ? context
        : args.length > 1
          ? { args: args.slice(1) }
          : {},
  }
}

function emit(level, method, args) {
  const payload = normalizePayload(level, args)
  if (level === 'debug' && !isDevelopment) return
  if (level === 'info' && !isDevelopment) return
  console[method](payload.message, payload.context)
}

export const logger = {
  info: (...args) => emit('info', 'log', args),
  warn: (...args) => emit('warn', 'warn', args),
  error: (...args) => emit('error', 'error', args),
  debug: (...args) => emit('debug', 'debug', args),
}

export default logger
