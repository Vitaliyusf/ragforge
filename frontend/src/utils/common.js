/** Utility functions for formatting data */

/**
 * Format file size in bytes to human-readable format
 * @param {number} bytes - File size in bytes
 * @returns {string} Formatted file size
 */
export function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

/**
 * Format a log line
 * @param {string} line - Log line
 * @returns {string} Formatted log line
 */
export function formatLogLine(line) {
  try {
    // Try to parse as JSON log entry
    const parsed = JSON.parse(line)
    const timestamp = new Date(parsed.timestamp).toLocaleString()
    return `[${timestamp}] [${parsed.service}] ${parsed.location}: ${parsed.message} ${parsed.data ? JSON.stringify(parsed.data) : ''}`
  } catch {
    // If not JSON, return as-is
    return line
  }
}

/**
 * Format timestamp to locale time string
 * @param {string|Date} timestamp - Timestamp
 * @returns {string} Formatted time
 */
export function formatTime(timestamp) {
  if (!timestamp) return ''
  try {
    return new Date(timestamp).toLocaleTimeString()
  } catch {
    return ''
  }
}

/**
 * Format message timestamp for display (e.g. "2:30 PM")
 * Handles ISO strings, Date objects, and locale time strings.
 * Shows "Just now" for messages within the last minute.
 * @param {string|Date|null} timestamp - Timestamp
 * @returns {string} Formatted time
 */
export function formatMessageTime(timestamp) {
  if (!timestamp) return ''
  try {
    const date = new Date(timestamp)
    if (isNaN(date.getTime())) return ''
    const now = new Date()
    const diffMs = now - date
    if (diffMs >= 0 && diffMs < 60_000) return 'Just now'
    return date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    })
  } catch {
    return ''
  }
}

/**
 * Format date for chat list (e.g. "Today", "Yesterday", "Jan 15")
 * @param {string|Date} dateStr - Date string or Date object
 * @returns {string} Formatted date
 */
export function formatChatDate(dateStr) {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return ''
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === today.toDateString()) return 'Today'
    if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

/**
 * Detect log severity from log line content
 * @param {string} line - Log line
 * @returns {string} Severity level (error, warning, info, debug, trace, unknown)
 */
export function detectLogSeverity(line) {
  if (!line || typeof line !== 'string') return 'unknown'
  
  const lowerLine = line.toLowerCase()
  
  // Try to parse as JSON first
  try {
    const parsed = JSON.parse(line)
    // Check for explicit severity fields
    if (parsed.severity) {
      const sev = parsed.severity.toLowerCase()
      if (sev.includes('error') || sev.includes('fatal') || sev.includes('critical')) return 'error'
      if (sev.includes('warn')) return 'warning'
      if (sev.includes('info')) return 'info'
      if (sev.includes('debug')) return 'debug'
      if (sev.includes('trace')) return 'trace'
    }
    // Check message field
    if (parsed.message) {
      const msg = parsed.message.toLowerCase()
      if (msg.includes('error') || msg.includes('exception') || msg.includes('fatal') || msg.includes('critical')) return 'error'
      if (msg.includes('warning') || msg.includes('warn')) return 'warning'
    }
  } catch {
    // Not JSON, continue with string matching
  }
  
  // Priority-based keyword matching (Error > Warning > Info > Debug > Trace)
  if (lowerLine.includes('error') || lowerLine.includes('exception') || 
      lowerLine.includes('fatal') || lowerLine.includes('critical')) {
    return 'error'
  }
  if (lowerLine.includes('warning') || lowerLine.includes('warn')) {
    return 'warning'
  }
  if (lowerLine.includes('info')) {
    return 'info'
  }
  if (lowerLine.includes('debug')) {
    return 'debug'
  }
  if (lowerLine.includes('trace')) {
    return 'trace'
  }
  
  return 'unknown'
}

/**
 * Get status icon component props
 * @param {string} status - Status value
 * @returns {Object} Status icon props
 */
export function getStatusIconProps(status) {
  const normalized = normalizeFileStatus(status)
  if (normalized === 'processing') {
    return {
      type: 'spinner',
      color: '#4a9eff'
    }
  } else if (normalized === 'complete') {
    return {
      type: 'check',
      color: '#10b981'
    }
  } else if (normalized === 'awaiting_review') {
    return {
      type: 'dot',
      color: '#f59e0b'
    }
  } else if (normalized === 'rejected' || normalized === 'error') {
    return {
      type: 'dot',
      color: '#ef4444'
    }
  } else {
    return {
      type: 'dot',
      color: '#6b7280'
    }
  }
}

/**
 * Get status color
 * @param {string} status - Status value
 * @returns {string} Color hex code
 */
export function getStatusColor(status) {
  const normalized = normalizeFileStatus(status)
  if (normalized === 'processing') {
    return '#4a9eff'
  } else if (normalized === 'complete') {
    return '#10b981'
  } else if (normalized === 'awaiting_review') {
    return '#f59e0b'
  } else if (normalized === 'rejected' || normalized === 'error') {
    return '#ef4444'
  } else {
    return '#6b7280'
  }
}

export function normalizeFileStatus(status) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'awaiting_review') return 'awaiting_review'
  if (['started', 'processing', 'resuming', 'running'].includes(normalized)) return 'processing'
  if (['complete', 'completed', 'ready', 'done'].includes(normalized)) return 'complete'
  if (normalized === 'rejected') return 'rejected'
  if (normalized === 'error') return 'error'
  return normalized || 'unknown'
}

/**
 * Computes the effective file status, using stage sub-fields to correct stale top-level status.
 * When the pipeline finishes all stages but the top-level status was not yet flushed to MongoDB,
 * this returns 'complete' rather than 'processing'.
 */
export function computeEffectiveStatus(file) {
  const topLevel = normalizeFileStatus(file?.status)

  // If already terminal, trust it
  if (['complete', 'rejected', 'awaiting_review', 'error'].includes(topLevel)) return topLevel

  const stage = file?.stage
  if (stage && typeof stage === 'object') {
    const values = Object.values(stage)
    if (values.length > 0) {
      if (values.some((v) => v === 'error')) return 'error'
      const DONE_VALUES = ['done', 'complete', 'completed', 'ready', 'skipped', 'not_required']
      if (values.every((v) => DONE_VALUES.includes(v))) return 'complete'
    }
  }

  return topLevel
}

const STATUS_LABELS = {
  complete: 'Complete',
  processing: 'Processing',
  awaiting_review: 'Awaiting Review',
  rejected: 'Rejected',
  error: 'Error',
  unknown: 'Unknown',
}

export function getFileStatusLabel(status) {
  const normalized = normalizeFileStatus(status)
  return STATUS_LABELS[normalized] ?? normalized.replace(/_/g, ' ')
}

export function getEffectiveStatusLabel(file) {
  const effective = computeEffectiveStatus(file)
  return STATUS_LABELS[effective] ?? effective.replace(/_/g, ' ')
}

export function getFileStatusBadgeVariant(status) {
  const normalized = normalizeFileStatus(status)
  if (normalized === 'complete') return 'success'
  if (normalized === 'awaiting_review' || normalized === 'processing') return 'warning'
  if (normalized === 'rejected' || normalized === 'error') return 'error'
  return 'default'
}

export function getEffectiveStatusBadgeVariant(file) {
  const effective = computeEffectiveStatus(file)
  return getFileStatusBadgeVariant(effective)
}

export function hasReviewPending(file) {
  return normalizeFileStatus(file?.status) === 'awaiting_review' || file?.review_status === 'pending'
}

/**
 * Check if summary is ready for a file
 * @param {Object} file - File object
 * @returns {boolean} True if summary is ready
 */
export function isSummaryReady(file) {
  return file.stage && file.stage.summary === 'done' && file.summary
}
