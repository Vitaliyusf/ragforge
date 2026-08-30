/** Formatting and severity detection for service log lines. */

/**
 * Correlation fields a structured log entry may carry, and what to call them.
 *
 * The order is the order the log viewer shows them in: the id that follows a
 * whole turn across services first, the narrower ones after.
 */
export const LOG_IDENTIFIER_FIELDS = Object.freeze([
  { field: 'trace_id', label: 'Trace', kindLabel: 'trace' },
  { field: 'correlation_id', label: 'Correlation', kindLabel: 'correlation' },
  { field: 'request_id', label: 'Request', kindLabel: 'request' },
  { field: 'turn_id', label: 'Turn', kindLabel: 'turn' },
  { field: 'conversation_id', label: 'Conversation', kindLabel: 'conversation' },
])

const IDENTIFIER_KEYS = new Set(LOG_IDENTIFIER_FIELDS.map((entry) => entry.field))

const KEYWORD_SEVERITY = [
  ['error', ['error', 'exception', 'fatal', 'critical']],
  ['warning', ['warning', 'warn']],
  ['info', ['info']],
  ['debug', ['debug']],
  ['trace', ['trace']],
]

function severityFromKeywords(text, levels = KEYWORD_SEVERITY) {
  for (const [severity, keywords] of levels) {
    if (keywords.some((keyword) => text.includes(keyword))) return severity
  }
  return null
}

/**
 * Detect the severity of a log line, preferring structured fields over
 * keyword matching.
 * @param {string} line
 * @returns {'error'|'warning'|'info'|'debug'|'trace'|'unknown'}
 */
export function detectLogSeverity(line) {
  if (!line || typeof line !== 'string') return 'unknown'
  const lowerLine = line.toLowerCase()

  try {
    const parsed = JSON.parse(line)
    if (parsed.severity) {
      const fromField = severityFromKeywords(String(parsed.severity).toLowerCase())
      if (fromField) return fromField
    }
    if (parsed.message) {
      // Only error/warning are trusted from free-text message bodies; the
      // quieter levels would match far too eagerly.
      const fromMessage = severityFromKeywords(
        String(parsed.message).toLowerCase(),
        KEYWORD_SEVERITY.slice(0, 2)
      )
      if (fromMessage) return fromMessage
    }
  } catch {
    // Not JSON — fall through to keyword matching on the raw line.
  }

  return severityFromKeywords(lowerLine) ?? 'unknown'
}

/**
 * Split one log line into the fields an operator reads and the raw text.
 *
 * Structured entries are presented as events — time, origin, message, and the
 * correlation ids that make them actionable — with the JSON kept as secondary
 * detail rather than as the primary rendering. A line that is not JSON is
 * still an event; it simply has nothing but its own text to offer, and is
 * marked `structured: false` so the viewer does not imply fields it invented.
 *
 * @param {string} line
 * @returns {{structured: boolean, timestamp: ?string, service: ?string,
 *   location: ?string, message: string, severity: string,
 *   identifiers: Array<{field: string, label: string, kindLabel: string, value: string}>,
 *   details: ?object, raw: string}}
 */
export function parseLogEvent(line) {
  const raw = typeof line === 'string' ? line : String(line ?? '')
  const severity = detectLogSeverity(raw)

  let parsed
  try {
    parsed = JSON.parse(raw)
  } catch {
    parsed = null
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return {
      structured: false,
      timestamp: null,
      service: null,
      location: null,
      message: raw,
      severity,
      identifiers: [],
      details: null,
      raw,
    }
  }

  // Ids are written at the top level by some services and inside `data` by
  // others. Both are read, and the top level wins, so one convention drifting
  // does not silently cost the viewer its links.
  const data = parsed.data && typeof parsed.data === 'object' && !Array.isArray(parsed.data)
    ? parsed.data
    : null
  const identifiers = LOG_IDENTIFIER_FIELDS.flatMap(({ field, label, kindLabel }) => {
    const value = parsed[field] ?? data?.[field]
    if (value == null || value === '') return []
    return [{ field, label, kindLabel, value: String(value) }]
  })

  // Whatever is left of `data` once the ids are pulled out and shown as
  // chips. Repeating them in the detail block would be the same fact twice.
  let details = null
  if (data) {
    const rest = Object.fromEntries(
      Object.entries(data).filter(([key]) => !IDENTIFIER_KEYS.has(key))
    )
    if (Object.keys(rest).length > 0) details = rest
  }

  return {
    structured: true,
    timestamp: parsed.timestamp ?? null,
    service: parsed.service ?? null,
    location: parsed.location ?? null,
    message: typeof parsed.message === 'string' ? parsed.message : raw,
    severity,
    identifiers,
    details,
    raw,
  }
}
