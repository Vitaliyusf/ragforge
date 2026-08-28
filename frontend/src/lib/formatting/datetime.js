/** Date and time formatting for display. */

/**
 * Format a message timestamp for display (e.g. "2:30 PM").
 * Handles ISO strings, Date objects and locale time strings, and reports
 * "Just now" for anything inside the last minute.
 * @param {string|Date|null} timestamp
 * @returns {string}
 */
export function formatMessageTime(timestamp) {
  if (!timestamp) return ''
  try {
    const date = new Date(timestamp)
    if (isNaN(date.getTime())) return ''
    const diffMs = new Date() - date
    if (diffMs >= 0 && diffMs < 60_000) return 'Just now'
    return date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    })
  } catch {
    return ''
  }
}

/**
 * Format a date for the chat list (e.g. "Today", "Yesterday", "Jan 15").
 * @param {string|Date} dateStr
 * @returns {string}
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
