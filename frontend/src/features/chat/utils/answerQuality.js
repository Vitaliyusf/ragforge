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
 *   2. A turn that retrieved nothing and declined to answer is not a low-scoring
 *      answer — it is a correct abstention, and it is described that way.
 *
 * Every function is pure so the presentation can be tested without a DOM.
 */

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

/** How many passages backed this answer, preferring the server's own count. */
export function countSources(sources, retrievalSummary) {
  if (Number.isFinite(retrievalSummary?.chunk_count)) return retrievalSummary.chunk_count
  return Array.isArray(sources) ? sources.length : 0
}

function groundingLabel(score) {
  if (!Number.isFinite(score) || score <= 0) return null
  if (score >= 0.75) return 'Grounded'
  if (score >= 0.5) return 'Partly grounded'
  return 'Weakly grounded'
}

const VERDICT_LABEL = {
  pass: 'Review passed',
  revise: 'Review flagged revisions',
  fail: 'Review failed',
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
 * Returns either an `abstention` shape — which states answerability and the
 * decision in words — or a `summary` shape whose `parts` are joined with
 * middots, e.g. `Grounded · 3 sources · Review passed`. `parts` is empty when
 * nothing was measured, and the caller renders nothing at all in that case.
 *
 * @param {{review?: object|null, sources?: Array|null, retrievalSummary?: object|null}} input
 */
export function buildAnswerQuality({ review, sources, retrievalSummary } = {}) {
  const sourceCount = countSources(sources, retrievalSummary)
  const measured = hasMeasuredScores(review)

  if (sourceCount === 0 && !measured) {
    return {
      kind: 'abstention',
      tone: 'neutral',
      sourceCount: 0,
      answerability: 'No supporting evidence',
      decision: 'Correctly abstained',
    }
  }

  const groundedness = Number.isFinite(review?.groundedness_score) && measured
    ? review.groundedness_score
    : null
  const verdict = review?.verdict || null
  const parts = [
    groundingLabel(groundedness),
    sourceCount > 0 ? `${sourceCount} source${sourceCount === 1 ? '' : 's'}` : null,
    VERDICT_LABEL[verdict] || null,
  ].filter(Boolean)

  return {
    kind: 'summary',
    tone: summaryTone(verdict, groundedness),
    sourceCount,
    verdict,
    groundedness,
    measured,
    parts,
  }
}
