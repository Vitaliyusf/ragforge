/** Text utility functions for Hebrew and RTL support */

/**
 * Detect if text contains Hebrew characters
 * @param {string} text - Text to check
 * @returns {boolean} True if text contains Hebrew
 */
export function containsHebrew(text) {
  if (!text || typeof text !== 'string') return false
  // Hebrew Unicode range: U+0590 to U+05FF
  const hebrewRegex = /[\u0590-\u05FF]/
  return hebrewRegex.test(text)
}

/**
 * Detect if text is primarily Hebrew (more than 50% Hebrew characters)
 * @param {string} text - Text to check
 * @returns {boolean} True if text is primarily Hebrew
 */
export function isPrimarilyHebrew(text) {
  if (!text || typeof text !== 'string') return false
  const hebrewChars = text.match(/[\u0590-\u05FF]/g) || []
  const totalChars = text.replace(/\s/g, '').length
  if (totalChars === 0) return false
  return hebrewChars.length / totalChars > 0.5
}

/**
 * Get text direction for mixed content
 * @param {string} text - Text to analyze
 * @returns {'ltr'|'rtl'|'auto'} Text direction
 */
export function getTextDirection(text) {
  if (!text || typeof text !== 'string') return 'ltr'
  if (isPrimarilyHebrew(text)) return 'rtl'
  if (containsHebrew(text)) return 'auto' // Mixed content
  return 'ltr'
}
