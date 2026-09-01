/**
 * Bidirectional text foundation.
 *
 * RagForge carries Hebrew and English side by side, often inside one string.
 * Two rules follow from that and they pull in opposite directions:
 *
 *   1. User-generated prose must be laid out in its own direction, so a
 *      Hebrew answer reads right-to-left even inside an LTR shell.
 *   2. Technical text — model ids, file names, chunk ids, hashes, JSON — must
 *      stay left-to-right no matter which direction surrounds it, otherwise
 *      the bidi algorithm reorders punctuation and the identifier becomes
 *      unreadable (`gpt-4o-mini.` renders as `.gpt-4o-mini`).
 *
 * Both rules are expressed here as prop factories rather than as classes, so
 * a caller cannot apply the alignment without also applying the direction.
 */

// Hebrew block: U+0590–U+05FF.
const HEBREW = /[\u0590-\u05FF]/
const HEBREW_GLOBAL = /[\u0590-\u05FF]/g

/**
 * Does the text contain any Hebrew at all?
 * @param {string} text
 * @returns {boolean}
 */
export function containsHebrew(text) {
  if (!text || typeof text !== 'string') return false
  return HEBREW.test(text)
}

/**
 * Is the text more than half Hebrew, ignoring whitespace?
 * @param {string} text
 * @returns {boolean}
 */
export function isPrimarilyHebrew(text) {
  if (!text || typeof text !== 'string') return false
  const hebrewChars = text.match(HEBREW_GLOBAL) || []
  const totalChars = text.replace(/\s/g, '').length
  if (totalChars === 0) return false
  return hebrewChars.length / totalChars > 0.5
}

/**
 * Resolve the base direction for a run of text.
 * Mixed content resolves to `auto` so the browser's own first-strong
 * heuristic decides per paragraph.
 * @param {string} text
 * @returns {'ltr'|'rtl'|'auto'}
 */
export function getTextDirection(text) {
  if (!text || typeof text !== 'string') return 'ltr'
  if (isPrimarilyHebrew(text)) return 'rtl'
  if (containsHebrew(text)) return 'auto'
  return 'ltr'
}

/**
 * Props for a block of user-generated text.
 *
 * Returns the resolved direction together with the matching logical text
 * alignment, so the two can never drift apart at a call site. Alignment uses
 * `text-start`, which follows `dir` rather than hard-coding a side.
 *
 * @param {string} text
 * @returns {{dir: 'ltr'|'rtl'|'auto', className: string, direction: 'ltr'|'rtl'|'auto'}}
 */
export function bidiTextProps(text) {
  const direction = getTextDirection(text)
  return { dir: direction, direction, className: 'text-start' }
}

/**
 * Props for a technical identifier that must stay left-to-right.
 *
 * `dir="ltr"` alone is not enough inside an RTL paragraph: the isolate keeps
 * the identifier from reordering the text around it as well.
 *
 * @returns {{dir: 'ltr', className: string}}
 */
export function ltrIsolateProps() {
  return { dir: 'ltr', className: 'inline-block [unicode-bidi:isolate]' }
}

/**
 * Props for a *block* of technical text — a log viewport, a JSON dump, a code
 * or preformatted section.
 *
 * The inline isolate above is wrong for these: a block that must never
 * reflow needs its own direction and its own left alignment regardless of the
 * interface locale, and `inline-block` would collapse a scrolling viewport.
 * Having one factory for this stops the alternative, which is thirty call
 * sites each writing `style={{ direction: 'ltr' }}` slightly differently.
 *
 * @returns {{dir: 'ltr', className: string}}
 */
export function techLtrProps() {
  return { dir: 'ltr', className: 'text-left [unicode-bidi:isolate]' }
}
