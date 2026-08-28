/** Formatting and severity detection for service log lines. */

/**
 * Render one log line for display, expanding structured JSON entries.
 * @param {string} line
 * @returns {string}
 */
export function formatLogLine(line) {
  try {
    const parsed = JSON.parse(line)
    const timestamp = new Date(parsed.timestamp).toLocaleString()
    return `[${timestamp}] [${parsed.service}] ${parsed.location}: ${parsed.message} ${
      parsed.data ? JSON.stringify(parsed.data) : ''
    }`
  } catch {
    return line
  }
}

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
