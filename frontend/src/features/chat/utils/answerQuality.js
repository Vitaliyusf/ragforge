/**
 * One vocabulary for "how good is this answer", shared by the compact summary
 * under an answer and by the Developer Inspector.
 *
 * Two facts drive everything here:
 *
 *   1. The judge's scores arrive coerced to `0.0` when the judge did not run,
 *      so a missing measurement and a genuinely terrible answer look identical
 *      in the payload. Rendering `0%` for the first case is a lie, so an
 *      all-zero review with nothing retrieved is treated as *unmeasured*.
 *   2. Nothing retrieved plus nothing measured says only that the answer has no
 *      supporting evidence. Whether the model *decided* to abstain is a
 *      judgement the backend does not currently report, so it is not inferred
 *      here — answerability is stated, and the decision is left unclaimed.
 *
 * User-facing counts speak of documents; chunk counts stay in the inspector.
 * See `./answerSources` for that grouping, which this module shares with the
 * source chips so the two can never disagree.
 *
 * Every function is pure so the presentation can be tested without a DOM —
 * which is also why the words come back twice: `parts` is the canonical
 * English, and `partKeys` is the same line as translation keys for the
 * component that renders it. This module has no locale of its own.
 */

import { DEFAULT_LOCALE } from '@/i18n/locale'
import { translate } from '@/i18n/translate'
import { countChunks, countDocumentSources } from './answerSources'

export const REVIEW_SCORE_KEYS = ['groundedness_score', 'completeness_score', 'safety_score']

/** Score (0..1) as a whole percentage, or `null` when it was never measured. */
export function toPercent(score) {
  return Number.isFinite(score) ? Math.round(score * 100) : null
}

/** Score as display text; unmeasured reads as an em dash, never as `0%`. */
export function formatScore(score) {
  const percent = toPercent(score)
  return percent == null ? '—' : `${percent}%`
}

/** Semantic colour for a 0..1 score, or the muted tone when unmeasured. */
export function scoreColor(score) {
  if (!Number.isFinite(score)) return 'var(--fg-soft)'
  if (score >= 0.75) return 'var(--success)'
  if (score >= 0.5) return 'var(--warning)'
  return 'var(--danger)'
}

/**
 * Did the judge actually produce scores?
 *
 * An all-zero triple is the shape a skipped review takes once the backend has
 * coerced its missing floats, so it counts as "not measured".
 */
export function hasMeasuredScores(review) {
  if (!review) return false
  const values = REVIEW_SCORE_KEYS.map((key) => review[key]).filter(Number.isFinite)
  return values.length > 0 && values.some((value) => value > 0)
}

function groundingLabelKey(score) {
  if (!Number.isFinite(score) || score <= 0) return null
  if (score >= 0.75) return 'chat.grounded'
  if (score >= 0.5) return 'chat.partlyGrounded'
  return 'chat.weaklyGrounded'
}

const VERDICT_LABEL_KEY = {
  pass: 'chat.reviewPassed',
  revise: 'chat.reviewRevise',
  fail: 'chat.reviewFailed',
}

function summaryTone(verdict, groundedness) {
  if (verdict === 'fail') return 'error'
  if (verdict === 'revise') return 'warning'
  if (Number.isFinite(groundedness) && groundedness > 0 && groundedness < 0.5) return 'warning'
  if (verdict === 'pass') return 'success'
  return 'neutral'
}

/**
 * The compact quality state shown under an answer by default.
 *
 * Returns either an `unsupported` shape — which states answerability in words
 * and claims nothing about intent — or a `summary` shape whose `parts` are
 * joined with middots, e.g. `Grounded · Sources: 2 · Review passed`. `parts`
 * is empty when nothing was measured, and the caller renders nothing at all
 * in that case. `partKeys` carries the same line as `{key, vars}` descriptors
 * for translation. `sourceCount` counts documents; `chunkCount` counts
 * passages.
 *
 * The source count is phrased as a labelled count rather than "2 sources"
 * because Hebrew plural agreement would otherwise need machinery that buys
 * nothing: "מקורות: 2" reads correctly for every number.
 *
 * @param {{review?: object|null, sources?: Array|null, retrievalSummary?: object|null}} input
 */
export function buildAnswerQuality({ review, sources, retrievalSummary } = {}) {
  const sourceCount = countDocumentSources(sources)
  const chunkCount = countChunks(sources, retrievalSummary)
  const measured = hasMeasuredScores(review)

  if (sourceCount === 0 && chunkCount === 0 && !measured) {
    return {
      kind: 'unsupported',
      tone: 'neutral',
      sourceCount: 0,
      chunkCount: 0,
      measured: false,
      answerability: translate(DEFAULT_LOCALE, 'chat.noSupportingEvidence'),
      answerabilityKey: 'chat.noSupportingEvidence',
      parts: [],
      partKeys: [],
    }
  }

  const groundedness = Number.isFinite(review?.groundedness_score) && measured
    ? review.groundedness_score
    : null
  const verdict = review?.verdict || null
  const groundingKey = groundingLabelKey(groundedness)
  const partKeys = [
    groundingKey ? { key: groundingKey } : null,
    sourceCount > 0 ? { key: 'chat.sourceCount', vars: { count: sourceCount } } : null,
    VERDICT_LABEL_KEY[verdict] ? { key: VERDICT_LABEL_KEY[verdict] } : null,
  ].filter(Boolean)

  return {
    kind: 'summary',
    tone: summaryTone(verdict, groundedness),
    sourceCount,
    chunkCount,
    verdict,
    groundedness,
    measured,
    parts: partKeys.map((part) => translate(DEFAULT_LOCALE, part.key, part.vars)),
    partKeys,
  }
}
