/** Byte-size formatting. */

const UNITS = ['Bytes', 'KB', 'MB', 'GB']

/**
 * Format a byte count as a human-readable size.
 * @param {number} bytes
 * @returns {string}
 */
export function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 Bytes'
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + UNITS[i]
}
